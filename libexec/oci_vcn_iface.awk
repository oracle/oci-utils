function prtiface(mac, iface, addr, sbits, state, vlan, vltag, secad) {
    if (iface != "") printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n", mac, iface, addr, sbits, state, vlan, vltag, secad
}
BEGIN { iface = ""; addr = "-" }
/^[0-9]/ {
    if (addr == "-") prtiface(mac, iface, addr, sbits, state, vlan, vltag, secad)
    addr = "-"
    sbits = "-"
    state = "-"
    macvlan = "-"
    vlan = "-"
    vltag = "-"
    secad = "-"
    if ($0 ~ /BROADCAST/ && $0 !~ /UNKNOWN/ && $0 !~ /NO-CARRIER/) {
        i = index($2, "@")
        if (1 < i) {
            j = index($2, ".")
            if (j < i) { # mac vlan (not used, no addrs)
                macvlan = substr($2, 1, i - 1)
                iface = substr($2, i + 1, length($2) - i - 1) # skip : at end
                 addr = ""
            } else { # vlan
                vlan = substr($2, 1, i - 1)
                # extract iface/vltag from macvlan
                iface = substr($2, i + 1, j - i - 1)
                vltag = substr($2, j + 1, length($2) - j - 1) # skip : at end
            }
        } else {
            i = index($2, ":")
            if (i <= 1) { print "cannot find interface name"; exit 1 }
            iface = substr($2, 1, i - 1)
        }
        if ($0 ~ /LOWER_UP/) state = "UP"
        else state = "DOWN"
    } else iface = ""
    next
}
/ link\/ether / { mac = tolower($2) }
/ inet [0-9]/ {
    i = index($2, "/")
    if (i <= 1) { print "cannot find interface inet address"; exit 1 }
    if (addr != "-") secad = "YES"
    addr = substr($2, 0, i - 1)
    sbits = substr($2, i + 1, length($2) - i)
    prtiface(mac, iface, addr, sbits, state, vlan, vltag, secad)
}
END { if (addr == "-") prtiface(mac, iface, addr, sbits, state, vlan, vltag, secad) }
