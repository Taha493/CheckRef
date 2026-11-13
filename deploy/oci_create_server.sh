#!/usr/bin/env bash
# Creates the CiteSure server on Oracle Cloud (Always Free) with the OCI command-line tool:
# network with ports 22/80/443 open, then an Ubuntu 24.04 Arm server (4 OCPUs, 24 GB, 100 GB
# disk). Safe to run again: existing pieces are reused. Retries while Oracle is out of
# capacity. Needs ~/.oci/config (API key) and the SSH key ~/.ssh/citesure.pub.
#
#   deploy/oci_create_server.sh            # 4 OCPUs / 24 GB
#   OCPUS=2 MEMORY=12 deploy/oci_create_server.sh
set -euo pipefail

NAME=citesure
OCPUS=${OCPUS:-4}
MEMORY=${MEMORY:-24}
DISK=${DISK:-100}
RETRY_SECONDS=${RETRY_SECONDS:-900}  # Oracle blocks addresses that ask too often
SSH_KEY=${SSH_KEY:-$HOME/.ssh/citesure.pub}
C=$(awk -F= '/^tenancy=/{print $2}' "$HOME/.oci/config")  # the root compartment

say() { printf '%s %s\n' "$(date +%H:%M:%S)" "$*"; }
none() { [[ -z "$1" || "$1" == "null" ]]; }

# ------------------------------------------------------------------ network
VCN=$(oci network vcn list -c "$C" --display-name "$NAME-vcn" --query 'data[0].id' --raw-output 2>/dev/null || true)
if none "$VCN"; then
  say "creating the network"
  VCN=$(oci network vcn create -c "$C" --display-name "$NAME-vcn" --cidr-blocks '["10.0.0.0/16"]' \
        --dns-label "$NAME" --wait-for-state AVAILABLE --query data.id --raw-output)
fi

IGW=$(oci network internet-gateway list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null || true)
if none "$IGW"; then
  say "creating the internet gateway"
  IGW=$(oci network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true \
        --display-name "$NAME-igw" --wait-for-state AVAILABLE --query data.id --raw-output)
fi

RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
oci network route-table update --rt-id "$RT" --force --route-rules \
  "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null

SL=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-security-list-id"' --raw-output)
tcp() { printf '{"source":"0.0.0.0/0","protocol":"6","isStateless":false,"tcpOptions":{"destinationPortRange":{"min":%s,"max":%s}}}' "$1" "$1"; }
icmp='{"source":"0.0.0.0/0","protocol":"1","isStateless":false,"icmpOptions":{"type":3,"code":4}}'
say "opening ports 22, 80 and 443"
oci network security-list update --security-list-id "$SL" --force \
  --ingress-security-rules "[$(tcp 22),$(tcp 80),$(tcp 443),$icmp]" \
  --egress-security-rules '[{"destination":"0.0.0.0/0","protocol":"all","isStateless":false}]' >/dev/null

SUBNET=$(oci network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output 2>/dev/null || true)
if none "$SUBNET"; then
  say "creating the public subnet"
  SUBNET=$(oci network subnet create -c "$C" --vcn-id "$VCN" --cidr-block 10.0.0.0/24 \
           --display-name "$NAME-subnet" --dns-label pub --route-table-id "$RT" \
           --security-list-ids "[\"$SL\"]" --wait-for-state AVAILABLE --query data.id --raw-output)
fi

# ------------------------------------------------------------------ server
# A server that already exists (also one still starting, e.g. after a timed-out request).
existing() {
  oci compute instance list -c "$C" --display-name "$NAME" \
    --query 'data[?"lifecycle-state"!=`TERMINATED` && "lifecycle-state"!=`TERMINATING`] | [0].id' \
    --raw-output 2>/dev/null || true
}
INSTANCE=$(existing)
if none "$INSTANCE"; then
  IMAGE=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "24.04" \
          --shape VM.Standard.A1.Flex --sort-by TIMECREATED --sort-order DESC --query 'data[0].id' --raw-output)
  mapfile -t ADS < <(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]", ' | grep .)
  say "image $(oci compute image get --image-id "$IMAGE" --query 'data."display-name"' --raw-output)"
  attempt=0
  while none "$INSTANCE"; do
    attempt=$((attempt + 1))
    for AD in "${ADS[@]}"; do
      INSTANCE=$(existing)
      if ! none "$INSTANCE"; then
        say "found the server from an earlier request; waiting until it runs"
        oci compute instance get --instance-id "$INSTANCE" --wait-for-state RUNNING >/dev/null
        break
      fi
      say "attempt $attempt: launching in $AD ($OCPUS OCPUs, $MEMORY GB)"
      # --no-retry: one request per attempt (the CLI otherwise retries failed launches itself).
      if out=$(oci --no-retry compute instance launch -c "$C" --availability-domain "$AD" --display-name "$NAME" \
                 --hostname-label "$NAME" --shape VM.Standard.A1.Flex \
                 --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEMORY}" --image-id "$IMAGE" \
                 --subnet-id "$SUBNET" --assign-public-ip true --boot-volume-size-in-gbs "$DISK" \
                 --ssh-authorized-keys-file "$SSH_KEY" --wait-for-state RUNNING \
                 --query data.id --raw-output 2>&1); then
        INSTANCE=$(tail -n1 <<<"$out")
        break
      fi
      if grep -qiE "capacity|LimitExceeded|TooManyRequests|InternalError|timed out|RequestException|Connection" <<<"$out"; then
        say "not available: $(grep -oiE 'out of (host )?capacity|LimitExceeded|TooManyRequests|InternalError|timed out|Connection[A-Za-z]*' <<<"$out" | head -n1)"
      else
        say "launch failed:"; echo "$out" >&2; exit 1
      fi
    done
    none "$INSTANCE" && { say "retrying in $RETRY_SECONDS s"; sleep "$RETRY_SECONDS"; }
  done
fi

IP=$(oci compute instance list-vnics --instance-id "$INSTANCE" --query 'data[0]."public-ip"' --raw-output)
say "SERVER READY: public IP $IP"
