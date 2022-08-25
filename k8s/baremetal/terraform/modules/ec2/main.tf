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
  instance_type               = "t2.medium"
  key_name                    = var.key_name
  subnet_id                   = var.vpc.public_subnets[0]
  vpc_security_group_ids      = [var.sg_k8smaster]

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
  
  # Copies the scrypt file to home dir
  provisioner "file" {
    source      = "./../k8smaster.sh"
    destination = "/home/ubuntu/k8smaster.sh"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }
  }

  //chmod script to be executable
  provisioner "remote-exec" {
    inline = [
      "chmod +x ~/k8smaster.sh",
      "nohup ./k8smaster.sh &"
    ]

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
  instance_type               = "t2.medium"
  key_name                    = var.key_name
  subnet_id                   = var.vpc.public_subnets[1]
  vpc_security_group_ids      = [var.sg_k8snode]

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
  
  # Copies the scrypt file to home dir
  provisioner "file" {
    source      = "./../k8snode.sh"
    destination = "/home/ubuntu/k8snode.sh"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }
  }

  //chmod script to be executable
  provisioner "remote-exec" {
    inline = [
      "chmod +x ~/k8snode.sh",
      "nohup ./k8snode.sh &"
    ]

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

  # lifecycle {
  #   prevent_destroy = true
  # }

  // Also an option to try:
  # lifecycle {
  #   create_before_destory = true
  # }
  tags = {
    "Name" = "${var.namespace}-k8smaster"
  }

}

###########   Add EIP elastic ip to the EC2
data "aws_eip" "eip" {
  # name        = "${var.namespace}-k8smaster"
  # depends_on  = [aws_eip.eip]
  public_ip   = "3.229.51.3"
}

# resource "aws_eip_association" "eip_assoc" {
#   instance_id   = aws_instance.k8smaster.id
#   allocation_id = data.aws_eip.eip.id
# }



