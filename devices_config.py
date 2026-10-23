from netmiko import ConnectHandler
from getpass import getpass


# 1. The data: one dictionary per switch (Phase-1)
switches = [
    {"name": "HQSW1", "site_id": 1, "pc_port": "Gi0/1", "lap_port": "Gi0/2",
     "mgmt_ip": "192.168.203.13", "loopback": "192.168.255.11",
     "uplink_ip": "192.168.100.2", "uplink_net": "192.168.100.0"},
    {"name": "HQSW2", "site_id": 2, "pc_port": "Gi0/1", "lap_port": "Gi0/2",
     "mgmt_ip": "192.168.203.14", "loopback": "192.168.255.12",
     "uplink_ip": "192.168.100.6", "uplink_net": "192.168.100.4"},
    {"name": "BRSW1", "site_id": 3, "pc_port": "Gi0/1", "lap_port": "Gi0/2",
     "mgmt_ip": "192.168.203.15", "loopback": "192.168.255.21",
     "uplink_ip": "192.168.100.10", "uplink_net": "192.168.100.8"},
    {"name": "BRSW2", "site_id": 4, "pc_port": "Gi0/1", "lap_port": "Gi0/2",
     "mgmt_ip": "192.168.203.16", "loopback": "192.168.255.22",
     "uplink_ip": "192.168.100.14", "uplink_net": "192.168.100.12"},
]

# 2.One dictionary per router (Phase 2), each with a list of its inside links
routers = [ 
    {"name": "R1", "mgmt_ip": "192.168.203.11", "loopback": "192.168.255.1",
     "links": [
         {"intf": "Gi0/5", "ip": "192.168.100.1", "net": "192.168.100.0"}, # to HQSW1
         {"intf": "Gi0/1", "ip": "192.168.100.5", "net": "192.168.100.4"}, # to HQSW2
         {"intf": "Gi0/2", "ip": "192.168.100.17", "net": "192.168.100.16"}, #to R2
     ]},
    {"name": "R2", "mgmt_ip": "192.168.203.12", "loopback": "192.168.255.2",
     "links": [
         {"intf": "Gi0/1", "ip": "192.168.100.9", "net": "192.168.100.8"}, # to BRSW1
         {"intf": "Gi0/2", "ip": "192.168.100.13", "net": "192.168.100.12"}, # to BRSW2
         {"intf" : "Gi0/0", "ip": "192.168.100.18", "net": "192.168.100.16"}, # to R1
     ]},
]


# 2. The switch rulebook: build the config lines for ONE switch
def build_switch_config(sw):
    site = str(sw["site_id"])          # number 1 -> text "1"
    lines = []                         # empty list, we fill it below

    # hostname and routing
    lines.append("hostname " + sw["name"])
    lines.append("ip routing")

    # the two VLANs
    lines.append("vlan 10")
    lines.append(" name STAFF")
    lines.append("vlan 20")
    lines.append(" name GUEST")

    # PC port -> Staff VLAN
    lines.append("interface " + sw["pc_port"])
    lines.append(" switchport mode access")
    lines.append(" switchport access vlan 10")
    lines.append(" spanning-tree portfast")

    # laptop port -> Guest VLAN
    lines.append("interface " + sw["lap_port"])
    lines.append(" switchport mode access")
    lines.append(" switchport access vlan 20")
    lines.append(" spanning-tree portfast")

    # gateways (SVIs): 192.168.<site>1.1 and 192.168.<site>2.1
    lines.append("interface Vlan10")
    lines.append(" ip address 192.168." + site + "1.1 255.255.255.0")
    lines.append(" no shutdown")
    lines.append("interface Vlan20")
    lines.append(" ip address 192.168." + site + "2.1 255.255.255.0")
    lines.append(" no shutdown")

    # DHCP: the switch hands out IPs to the PC and the laptop
    # .1 to .9 are kept free, so the first address handed out is .10
    lines.append("ip dhcp excluded-address 192.168." + site + "1.1 192.168." + site + "1.9")
    lines.append("ip dhcp excluded-address 192.168." + site + "2.1 192.168." + site + "2.9")
    lines.append("ip dhcp pool STAFF")
    lines.append(" network 192.168." + site + "1.0 255.255.255.0")
    lines.append(" default-router 192.168." + site + "1.1")
    lines.append("ip dhcp pool GUEST")
    lines.append(" network 192.168." + site + "2.0 255.255.255.0")
    lines.append(" default-router 192.168." + site + "2.1")
    
    # OSPF routing for switches to routers (Phase 2 Part-1)
    lines.append("interface Loopback0")
    lines.append(" ip address " + sw["loopback"] + " 255.255.255.255")
    lines.append("interface Gi0/0")
    lines.append(" no switchport")
    lines.append(" ip address " + sw["uplink_ip"] + " 255.255.255.252")
    lines.append(" no shutdown")
    lines.append("router ospf 1")
    lines.append(" router-id " + sw["loopback"])
    lines.append(" network 192.168." + site + "1.0 0.0.0.255 area 0")
    lines.append(" network 192.168." + site + "2.0 0.0.0.255 area 0")
    lines.append(" network " + sw["uplink_net"] + " 0.0.0.3 area 0")
    lines.append(" network " + sw["loopback"] + " 0.0.0.0 area 0")
    lines.append(" passive-interface Vlan10")
    lines.append(" passive-interface Vlan20")

    return lines

def build_router_conf(rt):
    lines = []
    lines.append("hostname " + rt["name"])

    # Loopback address
    lines.append("interface Loopback0")
    lines.append(" ip address " + rt["loopback"] + " 255.255.255.255")

    # IP assignment for each link: interface, IP, no shutdown
    for link in rt["links"]:
        lines.append("interface " + link["intf"])
        lines.append(" ip address " + link["ip"] + " 255.255.255.252")
        lines.append(" no shutdown")

    # OSPF routing for routers (Phase 2 Part 2)
    lines.append("router ospf 1")
    lines.append(" router-id " + rt["loopback"])
    lines.append(" network " + rt["loopback"] + " 0.0.0.0 area 0")
    for link in rt["links"]:
        lines.append(" network " + link["net"] + " 0.0.0.3 area 0")

    return lines


# 3. The pusher: send config lines to ONE device (switch or router) over SSH
def push_config(device, config, password):
    conn_info = {
        "device_type": "cisco_ios",
        "host": device["mgmt_ip"],
        "username": "admin",
        "password": password,
    }
    conn = ConnectHandler(**conn_info)     # log in over SSH
    output = conn.send_config_set(config)  # enter config mode, send every line
    conn.save_config()                     # write memory
    conn.disconnect()
    return output


# 4. The worker: for each switch, build, save, and push
password = getpass("Password: ")           # asked once, never stored in the file

for sw in switches:
    config = build_switch_config(sw)

    # save a copy of the config
    filename = sw["name"] + ".txt"
    with open(filename, "w") as f:
        for line in config:
            f.write(line + "\n")
    print("saved", filename)

    # push it to the switch; if this switch fails, report it and carry on
    print("Connecting to", sw["name"], "at", sw["mgmt_ip"], "...")
    try:
        output = push_config(sw, config, password)
        print(output)
        print("Pushed config to", sw["name"])
    except Exception as error:
        print("FAILED on", sw["name"], ":", error)

           
    print("-" * 40)
           
print("Done.")

for rt in routers:
    config = build_router_conf(rt)

    #save a copy of the conf
    filename = rt["name"] + ".txt"
    with open(filename, "w") as f:
        for line in config:
            f.write(line + "\n")
    print("saved", filename)

    #push it to the routers: if this router fails, report it and carry om
    print("Connecting to", rt["name"], "at", rt["mgmt_ip"], "...")
    try:
        output = push_config(rt, config, password)
        print(output)
        print("Pushed config to", rt["name"])
    except Exception as error:
        print("FAILED on", rt["name"], ":", error)

    print("-" * 40)

print("Done.")