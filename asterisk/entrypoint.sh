#!/bin/bash
# Generates the env-dependent PJSIP pieces, then runs Asterisk in the foreground.
set -e
GEN=/etc/asterisk/generated
mkdir -p "$GEN"

LOCAL_NET=${LOCAL_NET:-192.168.1.0/24}
OVH_USER=${OVH_USER:-}
OVH_DOMAIN=${OVH_DOMAIN:-}
OVH_PROXY=${OVH_PROXY:-}
PC_USER=${PC_USER:-pc}
PC_PASSWORD=${PC_PASSWORD:-changeme}

EXT_LINES=""
if [ -n "$OVH_PASSWORD" ]; then
  EXTERNAL_IP=${EXTERNAL_IP:-$(curl -fsS -m5 https://api.ipify.org || true)}
  [ -n "$EXTERNAL_IP" ] && EXT_LINES="external_signaling_address=$EXTERNAL_IP
external_media_address=$EXTERNAL_IP"
fi

cat > "$GEN/pjsip_transport.conf" <<EOT
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
local_net=$LOCAL_NET
local_net=127.0.0.0/8
$EXT_LINES
EOT

cat > "$GEN/pjsip_pc.conf" <<EOT
[pc]
type=endpoint
transport=transport-udp
context=from-pc
disallow=all
allow=alaw
allow=ulaw
allow=g722
auth=pc-auth
aors=pc
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
callerid="PC" <100>

[pc-auth]
type=auth
auth_type=userpass
username=$PC_USER
password=$PC_PASSWORD

[pc]
type=aor
max_contacts=5
remove_existing=yes
EOT

: > "$GEN/pjsip_ovh.conf"
if [ -n "$OVH_PASSWORD" ]; then
cat > "$GEN/pjsip_ovh.conf" <<EOT
[ovh-auth]
type=auth
auth_type=userpass
username=$OVH_USER
password=$OVH_PASSWORD

[ovh]
type=registration
transport=transport-udp
outbound_auth=ovh-auth
server_uri=sip:$OVH_DOMAIN
outbound_proxy=sip:$OVH_PROXY\;lr
client_uri=sip:$OVH_USER@$OVH_DOMAIN
contact_user=$OVH_USER
retry_interval=60
forbidden_retry_interval=300
fatal_retry_interval=300
expiration=600

[ovh]
type=aor
contact=sip:$OVH_DOMAIN
outbound_proxy=sip:$OVH_PROXY\;lr

[ovh]
type=endpoint
transport=transport-udp
context=from-ovh
disallow=all
allow=alaw
allow=ulaw
outbound_auth=ovh-auth
aors=ovh
from_user=$OVH_USER
from_domain=$OVH_DOMAIN
outbound_proxy=sip:$OVH_PROXY\;lr
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
dtmf_mode=rfc4733
t38_udptl=no

[ovh]
type=identify
endpoint=ovh
match=$OVH_PROXY
EOT
fi

exec asterisk -f -U root -G root
