terraform {
  required_version = "= 1.17.2"
}

removed {
  from = terraform_data.installation

  lifecycle {
    destroy = false
  }
}
