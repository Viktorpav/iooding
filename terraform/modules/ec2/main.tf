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
resource "aws_instance" "ec2_public" {
  ami                         = data.aws_ami.ubuntu.id
  associate_public_ip_address = true
  instance_type               = "t2.micro"
  key_name                    = var.key_name
  subnet_id                   = var.vpc.public_subnets[0]
  vpc_security_group_ids      = [var.sg_pub_id]

  tags = {
    "Name" = "${var.namespace}-ec2-public"
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

  provisioner "remote-exec" {
    inline = [
      "mkdir /home/ubuntu/.aws",
      "sudo chown -R ubuntu:ubuntu /home/ubuntu/.aws"
    ]

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }

  }

  provisioner "file" {
    source      = "./credentials"
    destination = "/home/ubuntu/.aws/credentials"

    connection {
      type        = "ssh"
      user        = "ubuntu"
      private_key = file("${var.key_name}.pem")
      host        = self.public_ip
    }

  }

}

// Configure the EC2 instance in a private subnet
resource "aws_instance" "ec2_private" {
  ami                         = data.aws_ami.ubuntu.id
  associate_public_ip_address = false
  instance_type               = "t2.micro"
  key_name                    = var.key_name
  subnet_id                   = var.vpc.private_subnets[1]
  vpc_security_group_ids      = [var.sg_priv_id]

  tags = {
    "Name" = "${var.namespace}-ec2-private"
  }

}

resource "aws_eip" "eip" {
  vpc      = true

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    "Name" = "${var.namespace}-ec2-public"
  }

}

resource "aws_eip_association" "eip_assoc" {
  instance_id   = aws_instance.ec2_public.id
  allocation_id = aws_eip.eip.id
}

/*
###########   Add EIP elastic ip to the EC2
data "aws_eip" "eip" {
  name   = "${var.namespace}-eip"
  depends_on = [aws_eip.eip]
  #public_ip = "3.73.165.22"
}
*/
