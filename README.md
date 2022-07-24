# iooding

The idea to create a skillet for my life try, like a blog, where people and I can store my ideas or things which interesting to post.

### Docs how to use:

Create aws user for web application to pull data from SSM
1. Install terraform
	*https://learn.hashicorp.com/tutorials/terraform/install-cli*
2. Get project from GitHub:
        git clone https://github.com/Viktorpav/iooding.git
		    cd iooding/terraform
    Run terraform iam-user module to create the user for boto3:
       terraform apply
    Run command to create a credentials file:
	```bash
(echo "[default]"; echo -n "aws_access_key_id = " & terraform output -raw access_key ; echo ""; echo -n "aws_secret_access_key = " ; terraform output -raw secret_key) > ./credentials
```
![5faa54eadf114799975224a7c64b25ec](https://user-images.githubusercontent.com/32811955/180643485-3c690a48-0d49-4b7c-8413-359a1dd8b0d7.png)



