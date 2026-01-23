/*
 * Copyright (C) 2020 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Modifications Copyright (C) 2024 Eastern Edge Robotics
 * Modifications by Zaid Duraid
 *
 * Description of modifications:
 * Functionality was added to allow the user to preset a custom volume and center of volume for links in the SDF.
 * This bypasses the need to add arbitrary internal collision shapes to complex models to calculate their volume and center of volume.
 */

#include <gz/msgs/wrench.pb.h>

#include <map>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <gz/common/Mesh.hh>
#include <gz/common/MeshManager.hh>
#include <gz/common/Profiler.hh>

#include <gz/plugin/Register.hh>

#include <gz/math/Helpers.hh>
#include <gz/math/Pose3.hh>
#include <gz/math/Vector3.hh>

#include <gz/msgs/Utility.hh>

#include <sdf/sdf.hh>

#include "gz/sim/components/CenterOfVolume.hh"
#include "gz/sim/components/Collision.hh"
#include "gz/sim/components/Gravity.hh"
#include "gz/sim/components/Inertial.hh"
#include "gz/sim/components/Link.hh"
#include "gz/sim/components/ParentEntity.hh"
#include "gz/sim/components/Pose.hh"
#include "gz/sim/components/Volume.hh"
#include "gz/sim/components/World.hh"

#include "gz/sim/Link.hh"
#include "gz/sim/Model.hh"
#include "gz/sim/Util.hh"

#include "EER_Buoyancy.hh"

using namespace gz;
using namespace sim;
using namespace systems;

//////////////////////////////////////////////////
// Helper: strip "WorldName::" prefix (one level)
static std::string RemoveWorldScope(const std::string &_name)
{
  return removeParentScope(_name, "::");
}

//////////////////////////////////////////////////
// Helper: strip model prefix if present: "rov::base_link" -> "base_link"
static std::string StripModelPrefix(const std::string &_nameNoWorld,
                                    const std::string &_modelName)
{
  if (_modelName.empty())
    return _nameNoWorld;

  const std::string prefix = _modelName + "::";
  if (_nameNoWorld.rfind(prefix, 0) == 0)
    return _nameNoWorld.substr(prefix.size());

  return _nameNoWorld;
}

//////////////////////////////////////////////////
// Helper: fuzzy match
// This makes "base_link" match:
//  - base_link
//  - rov::base_link
//  - base_link_fixed_joint_lump__Something
//  - rov::base_link_fixed_joint_lump__Something
static bool NameMatchesKey(const std::string &_candidate, const std::string &_key)
{
  if (_key.empty())
    return false;

  if (_candidate == _key)
    return true;

  // Candidate ends with "::key"
  if (_candidate.size() > _key.size())
  {
    const std::string suffix = "::" + _key;
    if (_candidate.size() >= suffix.size() &&
        _candidate.compare(_candidate.size() - suffix.size(), suffix.size(), suffix) == 0)
    {
      return true;
    }
  }

  // Candidate contains key (for fixed-joint lump names)
  if (_candidate.find(_key) != std::string::npos)
    return true;

  return false;
}

//////////////////////////////////////////////////
class gz::sim::systems::BuoyancyPrivate
{
  public: enum BuoyancyType
  {
    UNIFORM_BUOYANCY,
    GRADED_BUOYANCY
  };

  public: BuoyancyType buoyancyType{BuoyancyType::UNIFORM_BUOYANCY};

  public: double UniformFluidDensity(const math::Pose3d &_pose) const;

  public:
  template<typename T>
  void GradedFluidDensity(
    const math::Pose3d &_pose, const T &_shape, const math::Vector3d &_gravity);

  public: void CheckForNewEntities(const EntityComponentManager &_ecm);
  public: void CommitNewEntities(EntityComponentManager &_ecm);

  public: bool IsEnabled(Entity _entity, const EntityComponentManager &_ecm) const;
  public: bool CheckForPresetVolumes(Entity _entity, const EntityComponentManager &_ecm);

  public: Entity world{kNullEntity};
  public: std::string modelName{""};

  public: double fluidDensity{1000};
  public: std::map<double, double> layers;

  public: struct BuoyancyActionPoint
  {
    math::Vector3d force;
    math::Vector3d point;
    math::Pose3d pose;
  };

  public: std::vector<BuoyancyActionPoint> buoyancyForces;

  public: std::pair<math::Vector3d, math::Vector3d> ResolveForces(
    const math::Pose3d &_linkInWorld);

  public: std::unordered_set<std::string> enabled;
  public: std::unordered_map<std::string, std::pair<double, math::Vector3d>> presetVolumes;

  public: std::unordered_map<Entity, math::Vector3d> centerOfVolumes;
  public: std::unordered_map<Entity, double> volumes;

  // Track processed links so we only compute/apply once
  public: std::unordered_set<Entity> processedLinks;

  // Debug controls
  public: bool printedApplyOnce{false};
  public: bool printedNoBuoyancyWarn{false};
  public: bool printedLinkDump{false};
};

//////////////////////////////////////////////////
double BuoyancyPrivate::UniformFluidDensity(const math::Pose3d &/*_pose*/) const
{
  return this->fluidDensity;
}

//////////////////////////////////////////////////
template<typename T>
void BuoyancyPrivate::GradedFluidDensity(
  const math::Pose3d &_pose, const T &_shape, const math::Vector3d &_gravity)
{
  auto prevLayerFluidDensity = this->fluidDensity;
  auto prevLayerVol = 0.0;
  auto centerOfBuoyancy = math::Vector3d{0, 0, 0};

  for (const auto &[height, currFluidDensity] : this->layers)
  {
    math::Planed plane{math::Vector3d{0, 0, 1}, height - _pose.Pos().Z()};
    auto vol = _shape.VolumeBelow(plane);

    if (vol <= 0)
    {
      prevLayerFluidDensity = currFluidDensity;
      continue;
    }

    auto cov = _shape.CenterOfVolumeBelow(plane);
    if (!cov.has_value())
    {
      prevLayerFluidDensity = currFluidDensity;
      continue;
    }

    auto forceMag = -(vol - prevLayerVol) * _gravity * prevLayerFluidDensity;
    prevLayerFluidDensity = currFluidDensity;

    auto cob = (cov.value() * vol - centerOfBuoyancy * prevLayerVol)
             / (vol - prevLayerVol);

    centerOfBuoyancy = cov.value();

    this->buoyancyForces.push_back(BuoyancyActionPoint{forceMag, cob, _pose});
    prevLayerVol = vol;
  }

  auto vol = _shape.Volume();
  if (std::abs(vol - prevLayerVol) < 1e-10)
    return;

  auto forceMag = -(vol - prevLayerVol) * _gravity * prevLayerFluidDensity;

  auto cov = math::Vector3d{0, 0, 0};
  auto cob = (cov * vol - centerOfBuoyancy * prevLayerVol)
           / (vol - prevLayerVol);

  this->buoyancyForces.push_back(BuoyancyActionPoint{forceMag, cob, _pose});
}

//////////////////////////////////////////////////
std::pair<math::Vector3d, math::Vector3d> BuoyancyPrivate::ResolveForces(
  const math::Pose3d &_linkInWorld)
{
  auto force = math::Vector3d{0, 0, 0};
  auto torque = math::Vector3d{0, 0, 0};

  for (const auto &b : this->buoyancyForces)
  {
    force += b.force;

    math::Pose3d pointInCol{b.point, math::Quaterniond::Identity};
    auto pointInWorld = b.pose * pointInCol;
    auto offset = _linkInWorld.Pos() - pointInWorld.Pos();

    torque += b.force.Cross(offset);
  }

  return {force, torque};
}

//////////////////////////////////////////////////
// Fixed: use Each (not EachNew), and process each link once
void BuoyancyPrivate::CheckForNewEntities(const EntityComponentManager &_ecm)
{
  _ecm.Each<components::Link, components::Inertial>(
    [&](const Entity &_entity,
        const components::Link *,
        const components::Inertial *) -> bool
    {
      if (this->processedLinks.count(_entity))
        return true;

      this->processedLinks.insert(_entity);

      if (!this->printedLinkDump)
      {
        this->printedLinkDump = true;
        gzmsg << "\n[EER_Buoyancy] ==== LINK NAME DUMP (first time Each) ====\n";
        gzmsg << "[EER_Buoyancy] modelName='" << this->modelName << "'\n";
      }

      auto full = scopedName(_entity, _ecm, "::", false);
      auto noWorld = RemoveWorldScope(full);
      auto stripped = StripModelPrefix(noWorld, this->modelName);

      gzmsg << "[EER_Buoyancy] Seen link: full='" << full
            << "' noWorld='" << noWorld
            << "' stripped='" << stripped << "'\n";

      // Already has both => skip
      if (_ecm.EntityHasComponentType(_entity, components::CenterOfVolume().TypeId()) &&
          _ecm.EntityHasComponentType(_entity, components::Volume().TypeId()))
      {
        return true;
      }

      if (!this->IsEnabled(_entity, _ecm))
        return true;

      // Preset volume path
      if (this->CheckForPresetVolumes(_entity, _ecm))
      {
        gzmsg << "[EER_Buoyancy] Preset volume/COV applied to entity: "
              << full << std::endl;
        return true;
      }

      // Compute from collisions
      std::vector<Entity> collisions =
        _ecm.ChildrenByComponents(_entity, components::Collision());

      double volumeSum = 0.0;
      gz::math::Vector3d weightedPosInLinkSum = gz::math::Vector3d::Zero;

      for (const Entity &collision : collisions)
      {
        double volume = 0.0;

        const components::CollisionElement *coll =
          _ecm.Component<components::CollisionElement>(collision);

        if (!coll)
          continue;

        switch (coll->Data().Geom()->Type())
        {
          case sdf::GeometryType::BOX:
            volume = coll->Data().Geom()->BoxShape()->Shape().Volume();
            break;
          case sdf::GeometryType::SPHERE:
            volume = coll->Data().Geom()->SphereShape()->Shape().Volume();
            break;
          case sdf::GeometryType::CYLINDER:
            volume = coll->Data().Geom()->CylinderShape()->Shape().Volume();
            break;
          default:
            break;
        }

        volumeSum += volume;

        auto poseComp = _ecm.Component<components::Pose>(collision);
        if (poseComp)
          weightedPosInLinkSum += volume * poseComp->Data().Pos();
      }

      if (volumeSum > 0.0)
      {
        this->centerOfVolumes[_entity] = weightedPosInLinkSum / volumeSum;
        this->volumes[_entity] = volumeSum;

        gzmsg << "[EER_Buoyancy] Computed volume=" << volumeSum
              << " for entity: " << full << std::endl;
      }
      else
      {
        gzerr << "[EER_Buoyancy] Computed volume=0 for entity: " << full
              << " (no collision volume?)" << std::endl;
      }

      return true;
    });
}

//////////////////////////////////////////////////
// Fixed: only create component if missing
void BuoyancyPrivate::CommitNewEntities(EntityComponentManager &_ecm)
{
  for (const auto &kv : this->centerOfVolumes)
  {
    if (!_ecm.HasEntity(kv.first))
      continue;

    if (!_ecm.EntityHasComponentType(kv.first, components::CenterOfVolume().TypeId()))
    {
      _ecm.CreateComponent(kv.first, components::CenterOfVolume(kv.second));
    }
  }

  for (const auto &kv : this->volumes)
  {
    if (!_ecm.HasEntity(kv.first))
      continue;

    if (!_ecm.EntityHasComponentType(kv.first, components::Volume().TypeId()))
    {
      _ecm.CreateComponent(kv.first, components::Volume(kv.second));
    }
  }

  this->centerOfVolumes.clear();
  this->volumes.clear();
}

//////////////////////////////////////////////////
bool BuoyancyPrivate::IsEnabled(Entity _entity,
                               const EntityComponentManager &_ecm) const
{
  // If empty => everything enabled
  if (this->enabled.empty())
    return true;

  auto entity = _entity;
  while (entity != kNullEntity)
  {
    auto full = scopedName(entity, _ecm, "::", false);
    auto noWorld = RemoveWorldScope(full);
    auto stripped = StripModelPrefix(noWorld, this->modelName);

    for (const auto &k : this->enabled)
    {
      if (NameMatchesKey(full, k) || NameMatchesKey(noWorld, k) || NameMatchesKey(stripped, k))
        return true;
    }

    auto parentComp = _ecm.Component<components::ParentEntity>(entity);
    if (!parentComp)
      return false;

    entity = parentComp->Data();
  }

  return false;
}

//////////////////////////////////////////////////
bool BuoyancyPrivate::CheckForPresetVolumes(Entity _entity,
                                           const EntityComponentManager &_ecm)
{
  if (this->presetVolumes.empty())
    return false;

  auto full = scopedName(_entity, _ecm, "::", false);
  auto noWorld = RemoveWorldScope(full);
  auto stripped = StripModelPrefix(noWorld, this->modelName);

  for (const auto &kv : this->presetVolumes)
  {
    const auto &key = kv.first;

    if (NameMatchesKey(full, key) || NameMatchesKey(noWorld, key) || NameMatchesKey(stripped, key))
    {
      const double volume = kv.second.first;
      const math::Vector3d cov = kv.second.second;

      this->centerOfVolumes[_entity] = cov;
      this->volumes[_entity] = volume;

      gzmsg << "[EER_Buoyancy] Preset MATCHED\n"
            << "  key='" << key << "'\n"
            << "  entity full='" << full << "'\n"
            << "  entity noWorld='" << noWorld << "' stripped='" << stripped << "'\n"
            << "  volume=" << volume
            << " cov=(" << cov.X() << ", " << cov.Y() << ", " << cov.Z() << ")\n"
            << std::endl;

      return true;
    }
  }

  return false;
}

//////////////////////////////////////////////////
Buoyancy::Buoyancy()
  : dataPtr(std::make_unique<BuoyancyPrivate>())
{
}

//////////////////////////////////////////////////
void Buoyancy::Configure(const Entity &_entity,
                         const std::shared_ptr<const sdf::Element> &_sdf,
                         EntityComponentManager &_ecm,
                         EventManager &/*_eventMgr*/)
{
  gzmsg << "\n\n==== [EER_Buoyancy] CONFIGURE() CALLED ====\n" << std::endl;

  this->dataPtr->world = _entity;

  // Detect if attached to model or world
  const auto *gravityMaybe = _ecm.Component<components::Gravity>(_entity);
  auto full = scopedName(_entity, _ecm, "::", false);
  auto noWorld = RemoveWorldScope(full);

  if (!gravityMaybe)
  {
    this->dataPtr->modelName = noWorld;
    gzmsg << "[EER_Buoyancy] Attached to MODEL. modelName='"
          << this->dataPtr->modelName << "'\n";
  }
  else
  {
    gzmsg << "[EER_Buoyancy] Attached to WORLD.\n";
  }

  gzmsg << "[EER_Buoyancy] Configure entity full='" << full
        << "' noWorld='" << noWorld << "'\n";

  // Gravity from world (or find world)
  const components::Gravity *gravity =
    _ecm.Component<components::Gravity>(this->dataPtr->world);

  if (!gravity)
  {
    Entity foundWorld = kNullEntity;
    _ecm.Each<components::World>(
      [&](const Entity &_worldEntity, const components::World *) -> bool
      {
        foundWorld = _worldEntity;
        return false;
      });

    if (foundWorld != kNullEntity)
    {
      this->dataPtr->world = foundWorld;
      gravity = _ecm.Component<components::Gravity>(this->dataPtr->world);
      gzmsg << "[EER_Buoyancy] Found world entity automatically.\n";
    }
  }

  if (!gravity)
  {
    gzerr << "[EER_Buoyancy] Gravity NOT found. Buoyancy will not work.\n";
    return;
  }

  gzmsg << "[EER_Buoyancy] Gravity=("
        << gravity->Data().X() << ", "
        << gravity->Data().Y() << ", "
        << gravity->Data().Z() << ")\n";

  // Parse config
  if (_sdf->HasElement("uniform_fluid_density"))
  {
    this->dataPtr->fluidDensity = _sdf->Get<double>("uniform_fluid_density");
    gzmsg << "[EER_Buoyancy] uniform_fluid_density=" << this->dataPtr->fluidDensity << "\n";

    for (auto volumeElem = _sdf->FindElement("set_volume");
         volumeElem != nullptr;
         volumeElem = volumeElem->GetNextElement("set_volume"))
    {
      if (!volumeElem->HasElement("entity") ||
          !volumeElem->HasElement("volume") ||
          !volumeElem->HasElement("center_of_volume"))
      {
        gzerr << "[EER_Buoyancy] <set_volume> requires <entity>, <volume>, <center_of_volume>\n";
        continue;
      }

      std::string entityName = volumeElem->Get<std::string>("entity");
      double volume = volumeElem->Get<double>("volume");
      math::Vector3d cov = volumeElem->Get<math::Vector3d>("center_of_volume");

      this->dataPtr->presetVolumes[entityName] = {volume, cov};

      gzmsg << "[EER_Buoyancy] PresetVolume registered key='" << entityName
            << "' volume=" << volume
            << " cov=(" << cov.X() << ", " << cov.Y() << ", " << cov.Z() << ")\n";
    }
  }
  else if (_sdf->HasElement("graded_buoyancy"))
  {
    this->dataPtr->buoyancyType = BuoyancyPrivate::BuoyancyType::GRADED_BUOYANCY;
    gzmsg << "[EER_Buoyancy] Using GRADED_BUOYANCY.\n";
  }
  else
  {
    gzwarn << "[EER_Buoyancy] No <uniform_fluid_density> or <graded_buoyancy>. Default density=1000.\n";
  }

  // Enable tags
  if (_sdf->HasElement("enable"))
  {
    for (auto enableElem = _sdf->FindElement("enable");
         enableElem != nullptr;
         enableElem = enableElem->GetNextElement("enable"))
    {
      std::string key = enableElem->Get<std::string>();
      this->dataPtr->enabled.insert(key);
      gzmsg << "[EER_Buoyancy] Enable key added: '" << key << "'\n";
    }
  }
  else
  {
    gzmsg << "[EER_Buoyancy] No <enable> tags => buoyancy applies to ALL links.\n";
  }

  gzmsg << "==== [EER_Buoyancy] CONFIGURE() DONE ====\n\n" << std::endl;
}

//////////////////////////////////////////////////
void Buoyancy::PreUpdate(const UpdateInfo &_info, EntityComponentManager &_ecm)
{
  GZ_PROFILE("Buoyancy::PreUpdate");

  this->dataPtr->CheckForNewEntities(_ecm);
  this->dataPtr->CommitNewEntities(_ecm);

  if (_info.paused)
    return;

  const components::Gravity *gravity =
    _ecm.Component<components::Gravity>(this->dataPtr->world);

  if (!gravity)
  {
    gzerr << "[EER_Buoyancy] Gravity missing during PreUpdate.\n";
    return;
  }

  int appliedCount = 0;

  _ecm.Each<components::Link, components::Volume, components::CenterOfVolume>(
    [&](const Entity &_entity,
        const components::Link *,
        const components::Volume *_volume,
        const components::CenterOfVolume *_centerOfVolume) -> bool
    {
      math::Pose3d linkWorldPose = worldPose(_entity, _ecm);
      Link link(_entity);

      if (this->dataPtr->buoyancyType == BuoyancyPrivate::BuoyancyType::UNIFORM_BUOYANCY)
      {
        math::Vector3d buoyancy =
          -this->dataPtr->fluidDensity *
          _volume->Data() * gravity->Data();

        math::Vector3d offsetWorld =
          linkWorldPose.Rot().RotateVector(_centerOfVolume->Data());

        math::Vector3d torque = offsetWorld.Cross(buoyancy);

        link.AddWorldWrench(_ecm, buoyancy, torque);

        appliedCount++;

        if (!this->dataPtr->printedApplyOnce)
        {
          this->dataPtr->printedApplyOnce = true;

          auto full = scopedName(_entity, _ecm, "::", false);
          auto noWorld = RemoveWorldScope(full);
          auto stripped = StripModelPrefix(noWorld, this->dataPtr->modelName);

          gzmsg << "\n[EER_Buoyancy] BUOYANCY IS APPLYING\n"
                << "  entity full='" << full << "'\n"
                << "  noWorld='" << noWorld << "' stripped='" << stripped << "'\n"
                << "  volume=" << _volume->Data() << "\n"
                << "  fluidDensity=" << this->dataPtr->fluidDensity << "\n"
                << "  gravity=(" << gravity->Data().X() << ", "
                             << gravity->Data().Y() << ", "
                             << gravity->Data().Z() << ")\n"
                << "  buoyancyForce=(" << buoyancy.X() << ", "
                                    << buoyancy.Y() << ", "
                                    << buoyancy.Z() << ")\n"
                << "  torque=(" << torque.X() << ", "
                            << torque.Y() << ", "
                            << torque.Z() << ")\n"
                << std::endl;
        }
      }

      return true;
    });

  if (appliedCount == 0 && !this->dataPtr->printedNoBuoyancyWarn)
  {
    this->dataPtr->printedNoBuoyancyWarn = true;

    gzerr << "\n[EER_Buoyancy] NO BUOYANCY APPLIED\n"
          << "This means no entities had BOTH Volume + CenterOfVolume components.\n"
          << "Likely causes:\n"
          << "  1) <enable> name doesn't match real link name (fixed_joint_lump naming)\n"
          << "  2) No collisions / volume computed\n"
          << "  3) Preset key didn't match any link\n"
          << "Fix:\n"
          << "  - Remove <enable> tag to apply buoyancy to all links\n"
          << "  - Or set enable/entity to the real link name shown in LINK NAME DUMP\n"
          << std::endl;
  }
}

//////////////////////////////////////////////////
void Buoyancy::PostUpdate(const UpdateInfo &/*_info*/,
                          const EntityComponentManager &_ecm)
{
  this->dataPtr->CheckForNewEntities(_ecm);
}

//////////////////////////////////////////////////
bool Buoyancy::IsEnabled(Entity _entity,
                         const EntityComponentManager &_ecm) const
{
  return this->dataPtr->IsEnabled(_entity, _ecm);
}

GZ_ADD_PLUGIN(
  Buoyancy,
  System,
  Buoyancy::ISystemConfigure,
  Buoyancy::ISystemPreUpdate,
  Buoyancy::ISystemPostUpdate
)

GZ_ADD_PLUGIN_ALIAS(Buoyancy, "gz::sim::systems::EER_Buoyancy")
