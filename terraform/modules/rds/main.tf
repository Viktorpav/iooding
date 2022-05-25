resource "random_string" "rds_password" {
  length = 12
  special = true
  override_special = "!#$&"
}

resource "aws_ssm_parameter" "rds_password" {
  name  = "${var.namespace}-rds"
  type  = "SecureString"
  value = random_string.rds_password.result
}

data "aws_ssm_parameter" "rds_password_data" {
  name   = "${var.namespace}-rds"
  depends_on = [aws_ssm_parameter.rds_password]
}


resource "aws_db_instance" "rds" {
  identifier             = "${var.namespace}-rds"
  instance_class         = "db.t3.micro"
  allocated_storage      = 10
  engine                 = "postgres"
  engine_version         = "14.2"
  username               = "postgres"
  password               = data.aws_ssm_parameter.rds_password_data.value
  db_subnet_group_name   = var.sg_id
  vpc_security_group_ids = [var.sec_g_rds_id]
  #parameter_group_name   = "postgres14"
  publicly_accessible    = false
  skip_final_snapshot    = true
}
