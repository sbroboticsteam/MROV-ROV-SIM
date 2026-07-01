#include <gz/sim/System.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/components/JointPosition.hh>
#include <gz/sim/Util.hh>
#include <gz/plugin/Register.hh>

// #include <rclcpp/rclcpp.hpp>
// #include <std_msgs/msg/int32.hpp>

#include <gz/transport/Node.hh>
#include <gz/msgs/int32.pb.h>

#include <thread>
#include <cmath>
#include <stdint.h>

using namespace gz;
using namespace sim;
using namespace systems;

class BRT27 : 
    public System,
    public ISystemConfigure,
    public ISystemPostUpdate
{
    Entity jointEntity{kNullEntity};
    // rclcpp::Node::SharedPtr node;
    // rclcpp::Publisher<std_msgs::msg::Int32>::SharedPtr encoderPub;

    gz::transport::Node node;
    gz::transport::Node::Publisher pub;
    

    virtual void Configure(
        const Entity &_entity,
        const std::shared_ptr<const sdf::Element> &_sdf,
        EntityComponentManager &_ecm,
        EventManager &/*_eventMgr*/) override
    {
        auto model = Model(_entity);
        auto jointName = _sdf->Get<std::string>("joint_name");
        this->jointEntity = model.JointByName(_ecm, jointName);
        this->pub = this->node.Advertise<gz::msgs::Int32>("/encoders/" + jointName);
    }

    virtual void PostUpdate(
        const UpdateInfo &/*_info*/,
        const EntityComponentManager &_ecm) override
    {
        auto jointPosComp = _ecm.Component<components::JointPosition>(this->jointEntity);
        
        if (jointPosComp)
        {
            const auto &positions = jointPosComp->Data();

            if (!positions.empty())
            {
                double angle = positions[0];

                gz::msgs::Int32 msg;

                double wrapped = std::fmod(angle, 2.0 * M_PI);
                if (wrapped < 0)
                    wrapped += 2.0 * M_PI;

                msg.set_data(
                    static_cast<int32_t>(wrapped * 1024.0 / (2.0 * M_PI))
                );

                this->pub.Publish(msg);
            }
        }
    }
};

GZ_ADD_PLUGIN(
    BRT27,
    gz::sim::System,
    BRT27::ISystemConfigure,
    BRT27::ISystemPostUpdate)
GZ_ADD_PLUGIN_ALIAS(BRT27, "gz::sim::systems::BRT27")