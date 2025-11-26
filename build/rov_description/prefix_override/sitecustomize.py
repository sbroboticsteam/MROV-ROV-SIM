import sys
if sys.prefix == '/usr':
    sys.real_prefix = sys.prefix
    sys.prefix = sys.exec_prefix = '/home/odinroast/Desktop/MROV-ROV-SIM/install/rov_description'
