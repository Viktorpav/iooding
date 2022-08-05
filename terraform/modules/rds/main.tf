// Username for RDS
# data "aws_ssm_parameter" "rds_user_data" {
#   name   = "${var.namespace}_rds_user"
# }

// Password for RDS
resource "random_string" "rds_password" {
  length = 12
  special = true
  override_special = "!#$&"
}

resource "aws_ssm_parameter" "rds_password" {
  name      = "${var.namespace}_rds_password"
  type      = "SecureString"
  value     = random_string.rds_password.result
  overwrite = true
}

data "aws_ssm_parameter" "rds_password_data" {
  name   = "${var.namespace}_rds_password"
  depends_on = [aws_ssm_parameter.rds_password]
}

// RDS instance
resource "aws_db_instance" "rds" {
  identifier             = "${var.namespace}-rds"
  instance_class         = "db.t3.micro"
  allocated_storage      = 10
  engine                 = "postgres"
  engine_version         = "14.2"
  username               = "${var.namespace}_rds_user"
  #username               = data.aws_ssm_parameter.rds_user_data.value
  password               = data.aws_ssm_parameter.rds_password_data.value
  db_subnet_group_name   = var.sg_id
  vpc_security_group_ids = [var.sec_g_rds_id]
  #parameter_group_name   = "postgres14"
  publicly_accessible    = false
  skip_final_snapshot    = true
}
