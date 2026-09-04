#!/usr/bin/env bash
# Create the PRAHARI Lightsail instance from the CLI: instance + launch script + open ports + static IP,
# then poll the health endpoint until the app is up and print the HTTPS URL.
#
#   AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh            # create
#   AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh status     # show state and URL
#   AWS_PROFILE=prahari bash deploy/aws/lightsail-deploy.sh destroy    # delete instance and release the IP
#
# Requires: aws cli v2 with a profile that has deploy/aws/iam-policy.json. Region ap-south-1 (Mumbai).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="${PRAHARI_INSTANCE:-prahari-ews}"
REGION="${AWS_REGION:-ap-south-1}"
ZONE="${PRAHARI_ZONE:-${REGION}a}"
BUNDLE="${PRAHARI_BUNDLE:-small_3_1}"        # 2 GB RAM, 2 vCPU, 60 GB SSD, $12/month; medium_3_1 = 4 GB, $24
BLUEPRINT="${PRAHARI_BLUEPRINT:-ubuntu_24_04}"
IP_NAME="${NAME}-ip"
AWS="aws --region ${REGION} --output json"
cmd="${1:-create}"

ip_of() { $AWS lightsail get-static-ip --static-ip-name "$IP_NAME" 2>/dev/null | python -c "import sys,json; print(json.load(sys.stdin)['staticIp'].get('ipAddress',''))" 2>/dev/null || true; }
host_of() { local ip; ip="$(ip_of)"; [ -n "$ip" ] && echo "$(echo "$ip" | tr . -).sslip.io"; }

case "$cmd" in
  create)
    # user data must be LF; strip any CRLF a Windows checkout may have introduced
    # LF-only copy of the launch script in a path the AWS CLI can read on Windows too (no /tmp)
    UD="$HERE/.userdata.lf.sh"; tr -d '\r' < "$HERE/userdata.sh" > "$UD"
    sed -i "s|^BRANCH=.*|BRANCH=\"${PRAHARI_BRANCH:-main}\"|" "$UD"          # which branch the instance clones
    UD_URI="file://$(cygpath -w "$UD" 2>/dev/null || echo "$UD")"
    echo "creating instance $NAME ($BUNDLE, $BLUEPRINT) in $ZONE, cloning branch ${PRAHARI_BRANCH:-main} ..."
    $AWS lightsail create-instances --instance-names "$NAME" --availability-zone "$ZONE" \
        --blueprint-id "$BLUEPRINT" --bundle-id "$BUNDLE" --user-data "$UD_URI" \
        --tags key=project,value=idbi-innovate-prahari >/dev/null
    echo "waiting for the instance to be running ..."
    for i in $(seq 1 60); do
      st="$($AWS lightsail get-instance-state --instance-name "$NAME" | python -c "import sys,json; print(json.load(sys.stdin)['state']['name'])")"
      [ "$st" = "running" ] && break; sleep 5
    done
    echo "opening ports 80 and 443 ..."
    $AWS lightsail put-instance-public-ports --instance-name "$NAME" --port-infos \
        fromPort=22,toPort=22,protocol=tcp fromPort=80,toPort=80,protocol=tcp fromPort=443,toPort=443,protocol=tcp >/dev/null
    echo "allocating and attaching a static IP ..."
    $AWS lightsail allocate-static-ip --static-ip-name "$IP_NAME" >/dev/null 2>&1 || true
    $AWS lightsail attach-static-ip --static-ip-name "$IP_NAME" --instance-name "$NAME" >/dev/null
    HOST="$(host_of)"
    echo "instance up at $(ip_of); the launch script is installing Docker and building the image (5 to 10 minutes)."
    echo "polling https://${HOST}/api/health ..."
    for i in $(seq 1 120); do
      if curl -fsS --max-time 10 "https://${HOST}/api/health" 2>/dev/null | grep -q '"status":"ok"'; then
        echo; echo "PRAHARI is live:  https://${HOST}"; echo "health:           https://${HOST}/api/health"; exit 0
      fi
      sleep 10
    done
    echo "not healthy yet; check later with: bash $0 status   (or ssh ubuntu@$(ip_of) and read /var/log/prahari-build.log)"
    ;;
  status)
    $AWS lightsail get-instance --instance-name "$NAME" | python -c "import sys,json; i=json.load(sys.stdin)['instance']; print('state:', i['state']['name'], '| bundle:', i['bundleId'], '| ip:', i.get('publicIpAddress'))"
    HOST="$(host_of)"; [ -n "$HOST" ] && { echo "url: https://${HOST}"; curl -sS --max-time 10 "https://${HOST}/api/health" || true; echo; }
    ;;
  destroy)
    echo "deleting $NAME and releasing $IP_NAME ..."
    $AWS lightsail detach-static-ip --static-ip-name "$IP_NAME" >/dev/null 2>&1 || true
    $AWS lightsail release-static-ip --static-ip-name "$IP_NAME" >/dev/null 2>&1 || true
    $AWS lightsail delete-instance --instance-name "$NAME" >/dev/null
    echo "done; billing for this instance has stopped."
    ;;
  *) echo "usage: $0 [create|status|destroy]"; exit 2 ;;
esac
