# Traktor veje-system


## Hardware

**Router - Teltonika RUT956:**
<https://www.teltonika-networks.com/products/routers/rut956>

**RS232 serial device server - Moxa NPort 5410:**
<https://www.moxa.com/en/products/industrial-edge-connectivity/serial-device-servers/general-device-servers/nport-5400-series/nport-5410>

**Scales - Mettler Toledo ICS425:**
<https://www.mt.com/dk/da/home/products/Transport_and_Logistics_Solutions/postal_scales_transp_log/basic-postal-scales.html>

## Connections

```mermaid
flowchart LR
    scale1["Scale 1<br/>Mettler Toledo ICS425"]
    scale2["Scale 2<br/>Mettler Toledo ICS425"]
    relay["Relay bank"]
    moxa["Moxa NPort 5410<br/>Serial device server"]
    router["Teltonika RUT956<br/>Router"]
    pc["PC<br/>Teltonika Data API"]
    wifi(("WiFi<br/>antenna"))
    gnss(("GNSS<br/>antenna"))
    lte(("LTE<br/>antenna"))

    scale1 -- "RS232 (port 1)" --> moxa
    scale2 -- "RS232 (port 2)" --> moxa
    relay -- "RS232 (port 4)" --> moxa
    moxa -- "Ethernet" --> router
    router -- "Ethernet" --> pc
    router --- wifi
    router --- gnss
    router --- lte
```