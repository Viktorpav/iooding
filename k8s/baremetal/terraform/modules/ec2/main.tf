// Create aws_ami filter to pick up the ami available in your region
data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

// Configure the EC2 instance in a public subnet
resource "aws_instance" "k8smaster" {
  ami                         = data.aws_ami.ubuntu.id
  associate_public_ip_address = true
  instance_type               = "t3.medium"
  key_name                    = var.key_name
  subnet_id                   = var.vpc.public_subnets[0]
  vpc_security_group_ids      = [var.sg_k8smaster]

  user_data = <<EOF
#!/bin/bash
hostname="k8smaster"
sudo hostnamectl set-hostname $hostname
host $hostname | grep -m1 $hostname | awk -v hostname=$hostname '{print $4, hostname}' | sudo tee -a /etc/hosts > /dev/null

sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab
sudo swapoff -a

sudo tee /etc/modules-load.d/containerd.conf <<EOF1
overlay
br_netfilter
EOF1

sudo modprobe overlay
sudo modprobe br_netfilter

cat <<EOF2 | sudo tee /etc/sysctl.d/99-kubernetes-cri.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF2

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

sudo kubeadm init --control-plane-endpoint=k8smaster --cri-socket /run/containerd/containerd.sock

mkdir -p $HOME/.kube
sudo cp -f /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

curl https://raw.githubusercontent.com/projectcalico/calico/master/manifests/calico.yaml -O
kubectl apply -f calico.yaml


# kubeadm token create --print-join-command
# -/////////////////-
# https://thenewstack.io/how-to-deploy-kubernetes-with-kubeadm-and-containerd/
# https://www.linuxtechi.com/install-kubernetes-on-ubuntu-22-04/
EOF

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    "Name" = "${var.namespace}-k8smaster"
  }

  # Copies the ssh key file to home dir
  provisioner "file" {
    source      = "./${var.key_name}.pem"
    destination = "/home/ubuntu/${var.key_name}.pem"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }
  }
  
  //chmod key 400 on EC2 instance
  provisioner "remote-exec" {
    inline = ["chmod 400 ~/${var.key_name}.pem"]

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }
  }

}

// Configure the EC2 instance in a private subnet
resource "aws_instance" "k8snode" {
  ami                         = data.aws_ami.ubuntu.id
  associate_public_ip_address = true
  instance_type               = "t3.medium"
  key_name                    = var.key_name
  subnet_id                   = var.vpc.public_subnets[0]
  vpc_security_group_ids      = [var.sg_k8snode]

  user_data = templatefile("${path.module}/k8snode.sh", {k8smaster_private_ip = "${aws_instance.k8smaster.private_ip}"})

  tags = {
    "Name" = "${var.namespace}-k8snode"
  }

  # Copies the ssh key file to home dir
  provisioner "file" {
    source      = "./${var.key_name}.pem"
    destination = "/home/ubuntu/${var.key_name}.pem"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }
  }
  
  //chmod key 400 on EC2 instance
  provisioner "remote-exec" {
    inline = ["chmod 400 ~/${var.key_name}.pem"]

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }
  }

}

resource "aws_eip" "eip" {
  vpc      = true
  depends_on = [aws_instance.k8smaster]
  # lifecycle {
  #   prevent_destroy = true
  # }

  // Also an option to try:
  lifecycle {
    create_before_destroy = true
  }
  tags = {
    "Name" = "${var.namespace}-k8smaster"
  }

}

// Add EIP elastic ip to the EC2
# data "aws_eip" "eip" {
#   depends_on  = [aws_eip.eip]
#   tags = {
#     Name = "${var.namespace}-k8smaster"
#   }
#   # public_ip   = "44.210.5.0"
# }

resource "aws_eip_association" "eip_assoc" {
  instance_id   = aws_instance.k8smaster.id
  allocation_id = aws_eip.eip.id
  # allocation_id = data.aws_eip.eip.id
}