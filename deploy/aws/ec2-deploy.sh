#!/usr/bin/env bash
# PRAHARI on a single EC2 instance (fallback when credits do not cover Lightsail). Creates a key pair,
# a security group (22, 80, 443), a t4g.small Ubuntu 24.04 ARM instance with deploy/aws/userdata.sh,
# an Elastic IP, then polls the health endpoint and prints the HTTPS URL (Caddy + sslip.io).
#
#   AWS_PROFILE=prahari bash deploy/aws/ec2-deploy.sh            # create
#   AWS_PROFILE=prahari bash deploy/aws/ec2-deploy.sh status
#   AWS_PROFILE=prahari bash deploy/aws/ec2-deploy.sh destroy    # terminate + release the Elastic IP
set -euo pipefail
export MSYS_NO_PATHCONV=1            # Git Bash on Windows must not rewrite /dev/sda1 into a Windows path
HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="${PRAHARI_INSTANCE:-prahari-ews}"
REGION="${AWS_REGION:-ap-south-1}"
TYPE="${PRAHARI_EC2_TYPE:-t4g.small}"          # Graviton; use t3.small for x86
AWS="aws --region ${REGION} --output text"
cmd="${1:-create}"
STATE_FILE="$HERE/.ec2-state-${NAME}"

case "$cmd" in
  create)
    # newest Canonical Ubuntu 24.04 (noble) AMI for the instance architecture (owner 099720109477 = Canonical)
    ARCH="arm64"; case "$TYPE" in t3.*|t2.*|m5.*|c5.*|m6i.*|c6i.*) ARCH="amd64";; esac
    AMI="$($AWS ec2 describe-images --owners 099720109477 \
          --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-${ARCH}-server-*" "Name=state,Values=available" \
          --query 'sort_by(Images,&CreationDate)[-1].ImageId')"
    [ -n "$AMI" ] && [ "$AMI" != "None" ] || { echo "no Ubuntu 24.04 ${ARCH} AMI found in $REGION"; exit 1; }
    VPC="$($AWS ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId')"
    SUBNET="$($AWS ec2 describe-subnets --filters Name=vpc-id,Values="$VPC" --query 'Subnets[0].SubnetId')"
    echo "ami $AMI, vpc $VPC, subnet $SUBNET"
    if ! $AWS ec2 describe-key-pairs --key-names "$NAME" >/dev/null 2>&1; then
      $AWS ec2 create-key-pair --key-name "$NAME" --query KeyMaterial > "$HERE/${NAME}.pem"; chmod 600 "$HERE/${NAME}.pem"
      echo "ssh key saved to deploy/aws/${NAME}.pem (keep it private; it is gitignored)"
    fi
    SG="$($AWS ec2 describe-security-groups --filters Name=group-name,Values="$NAME" Name=vpc-id,Values="$VPC" --query 'SecurityGroups[0].GroupId' 2>/dev/null || true)"
    if [ -z "$SG" ] || [ "$SG" = "None" ]; then
      SG="$($AWS ec2 create-security-group --group-name "$NAME" --description "PRAHARI demo" --vpc-id "$VPC" --query GroupId)"
      for p in 22 80 443; do $AWS ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port "$p" --cidr 0.0.0.0/0 >/dev/null; done
    fi
    UD="$HERE/.userdata.lf.sh"; tr -d '\r' < "$HERE/userdata.sh" > "$UD"
    sed -i "s|^BRANCH=.*|BRANCH=\"${PRAHARI_BRANCH:-main}\"|" "$UD"
    UD_URI="file://$(cygpath -w "$UD" 2>/dev/null || echo "$UD")"
    IID="$($AWS ec2 run-instances --image-id "$AMI" --instance-type "$TYPE" --key-name "$NAME" --security-group-ids "$SG" \
          --subnet-id "$SUBNET" --associate-public-ip-address --user-data "$UD_URI" \
          --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":16,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
          --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME},{Key=project,Value=idbi-innovate-prahari}]" \
          --query 'Instances[0].InstanceId')"
    echo "instance $IID launching ..."; $AWS ec2 wait instance-running --instance-ids "$IID"
    ALLOC="$($AWS ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$NAME}]" --query AllocationId)"
    $AWS ec2 associate-address --instance-id "$IID" --allocation-id "$ALLOC" >/dev/null
    IP="$($AWS ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp')"
    printf 'IID=%s\nALLOC=%s\nSG=%s\nIP=%s\n' "$IID" "$ALLOC" "$SG" "$IP" > "$STATE_FILE"
    HOST="$(echo "$IP" | tr . -).sslip.io"
    echo "public ip $IP; the launch script is installing Docker and building the image (5 to 10 minutes)."
    for i in $(seq 1 120); do
      if curl -fsS --max-time 10 "https://${HOST}/api/health" 2>/dev/null | grep -q '"status":"ok"'; then
        echo; echo "PRAHARI is live:  https://${HOST}"; echo "ssh: ssh -i deploy/aws/${NAME}.pem ubuntu@${IP}"; exit 0
      fi
      sleep 10
    done
    echo "not healthy yet; check with: bash $0 status   (or ssh -i deploy/aws/${NAME}.pem ubuntu@${IP} and read /var/log/prahari-build.log)"
    ;;
  status)
    [ -f "$STATE_FILE" ] || { echo "no state file; nothing created from here"; exit 1; }
    . "$STATE_FILE"
    $AWS ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].[State.Name,InstanceType,PublicIpAddress]'
    HOST="$(echo "$IP" | tr . -).sslip.io"; echo "url: https://${HOST}"; curl -sS --max-time 10 "https://${HOST}/api/health" || true; echo
    ;;
  destroy)
    [ -f "$STATE_FILE" ] || { echo "no state file"; exit 1; }
    . "$STATE_FILE"
    $AWS ec2 terminate-instances --instance-ids "$IID" >/dev/null; $AWS ec2 wait instance-terminated --instance-ids "$IID"
    $AWS ec2 release-address --allocation-id "$ALLOC" >/dev/null || true
    $AWS ec2 delete-security-group --group-id "$SG" >/dev/null || true
    rm -f "$STATE_FILE"; echo "terminated; billing has stopped."
    ;;
  *) echo "usage: $0 [create|status|destroy]"; exit 2 ;;
esac
