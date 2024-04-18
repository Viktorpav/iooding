#!/bin/bash
export MASTER_NODE_IP=$(hostname -I | awk '{print $1}')
export K8S_POD_NETWORK_CIDR="10.244.0.0/16"
hostname=$(hostname)
echo "$MASTER_NODE_IP   $hostname" | sudo tee -a /etc/hosts > /dev/null

sudo sed -ri '/\sswap\s/s/^#?/#/' /etc/fstab
sudo swapoff -a

sudo tee /etc/modules-load.d/containerd.conf <<EOF
overlay
br_netfilter
EOF

sudo tee /etc/sysctl.d/99-kubernetes-cri.conf <<EOF
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
net.netfilter.nf_conntrack_max = 262144
EOF

sudo sysctl --system

#Containerd configuration
sudo apt update -y && sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt -y install containerd gnupg2 software-properties-common apt-transport-https ca-certificates conntrack iptables ebtables ethtool socat
sudo systemctl enable --now containerd

sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml

sudo sed -i 's/SystemdCgroup \= false/SystemdCgroup \= true/g' /etc/containerd/config.toml
sudo sed -i 's/disabled_plugins = \[\]/\#disabled_plugins \= \[\"cri\"\]/g' /etc/containerd/config.toml

sudo mkdir -p /etc/systemd/system/containerd.service.d/
echo -e "[Service]\nExecStartPre=" | sudo tee /etc/systemd/system/containerd.service.d/00-nomodprobe.conf > /dev/null

sudo systemctl daemon-reload
sudo systemctl restart containerd

#Kub install
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
#Helm install
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install -y kubelet kubeadm kubectl helm
sudo apt-mark hold kubelet kubeadm kubectl

sudo crictl config runtime-endpoint unix:///var/run/containerd/containerd.sock

sudo systemctl enable --now kubelet

sudo kubeadm init --pod-network-cidr=$K8S_POD_NETWORK_CIDR

mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

echo "Environment=\"KUBELET_EXTRA_ARGS=--node-ip=$MASTER_NODE_IP\"" | sudo tee /etc/sysconfig/kubelet

sudo systemctl daemon-reload
sudo systemctl restart kubelet

kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml

### Works!!!




# # Install Cilium
# CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
# CLI_ARCH=amd64
# if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi
# curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}
# sha256sum --check cilium-linux-${CLI_ARCH}.tar.gz.sha256sum
# sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
# rm cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}

# cilium install --version 1.15.3

# helm repo add cilium https://helm.cilium.io/
# helm install cilium cilium/cilium --version 1.15.3 -n kube-system \
#   --set ipam.operator.ipam.operator.clusterPoolIPv4PodCIDRList=10.42.0.0/16 \
#   --set ipv4NativeRoutingCIDR=10.42.0.0/16 \
#   --set ipv4.enabled=true \
#   --set loadBalancer.mode=dsr \
#   --set kubeProxyReplacement=strict \
#   --set tunnel=disabled \
#   --set autoDirectNodeRoutes=true


# cilium install --helm-set=cluster.name=$hostname \
#                --helm-set=ipam.mode=kubernetes \
#                --helm-set=kubernetesNode.nodeInitDropInConfigMap.enabled=true \
#                --helm-set=kubernetesNode.nodeInitDropInConfigMap.name=cilium-config \
#                --helm-set=tunnel=disabled \
#                --helm-set=masquerade=strict \
#                --helm-set=hostServices.enabled=false \
#                --helm-set=externalIPs.enabled=true \
#                --helm-set=nodePort.enabled=true \
#                --helm-set=hostPort.enabled=true \
#                --helm-set=endpointRoutes.enabled=true \
#                --helm-set=operator.unmanagedWebhookURLIPs=39.96.85.252/24 \
#                --helm-set=operator.unmanagedWebhookURLIPs=198.18.0.0/15 \
#                --helm-set=nodeInitConfiguration.enabled=true \
#                --helm-set=enableIPSec=false \
#                --helm-set=ipv6.enabled=false \
#                --helm-set=securityGroup.enabled=true \
#                --helm-set=hostServices.enabled=true \
#                --helm-set=hostServices.protocols=tcp \
#                --helm-set=hostServices.protocols=udp \
#                --helm-set=devices={} > cilium_install_output.yaml
# sudo -H -u ubuntu kubectl apply -f cilium_install_output.yaml
