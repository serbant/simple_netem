# simple_netem

Simple Netem Control
====================

Expose network (WAN) emulation control functions on linux hosts in Python code

The linux commands exposed are *tc* and *ip*.
See 
http://www.linuxfoundation.org/collaborate/workgroups/networking/netem#Emulating_wide_area_network_delays
for details

Supported WAN Emulations
------------------------

This module can provide any combination of the WAN conditions (emulations)
listed below but only on a per network interface basis. It does not support
per flow emulations.

* packet delay

* packet loss

* packet duplication

* packet corruption

* packet re-ordering

* traffic rate


Handling user privileges
------------------------

See the config/simple_netem_sudoers for details