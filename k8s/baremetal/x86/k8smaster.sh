#!/bin/bash
# USER=root - read more about this
hostname="k8smaster"
dir="/home/ubuntu"
sudo hostnamectl set-hostname $hostname
host $hostname | grep -m1 $hostname | awk -v hostname=$hostname '{print $4, hostname}' | sudo tee -a /etc/hosts > /dev/null

sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
sudo swapoff -a

sudo tee /etc/modules-load.d/containerd.conf <<EOF
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

cat <<EOF | sudo tee /etc/sysctl.d/99-kubernetes-cri.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF

sudo sysctl --system

curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" -y
sudo apt update -y && sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
sudo DEBIAN_FRONTEND=noninteractive apt -y install containerd gnupg2 software-properties-common apt-transport-https ca-certificates

sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml >/dev/null 2>&1
sudo sed -i 's/SystemdCgroup \= false/SystemdCgroup \= true/g' /etc/containerd/config.toml

sudo systemctl restart containerd
sudo systemctl enable containerd

curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
sudo apt-add-repository "deb http://apt.kubernetes.io/ kubernetes-xenial main" -y

sudo apt update -y && sudo apt -y install kubelet kubeadm kubectl 
sudo apt-mark hold kubelet kubeadm kubectl

sudo systemctl enable --now kubelet

sudo kubeadm init --pod-network-cidr=192.168.0.0/16 --control-plane-endpoint=k8smaster --cri-socket /run/containerd/containerd.sock

cd $dir
sudo -H -u ubuntu mkdir -p $dir/.kube
sudo cp -f /etc/kubernetes/admin.conf $dir/.kube/config
sudo chown ubuntu:ubuntu $dir/.kube/config

sudo -H -u ubuntu curl https://raw.githubusercontent.com/projectcalico/calico/master/manifests/calico.yaml -O
sudo -H -u ubuntu kubectl apply -f calico.yaml

# sudo kubeadm token create --print-join-command

# -/////////////////-
# https://thenewstack.io/how-to-deploy-kubernetes-with-kubeadm-and-containerd/
# https://www.linuxtechi.com/install-kubernetes-on-ubuntu-22-04/

