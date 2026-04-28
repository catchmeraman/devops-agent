output "cluster_endpoint"        { value = aws_rds_cluster.main.endpoint }
output "reader_endpoint"         { value = aws_rds_cluster.main.reader_endpoint }
output "cluster_identifier"      { value = aws_rds_cluster.main.cluster_identifier }
output "secret_arn"              { value = aws_rds_cluster.main.master_user_secret[0].secret_arn }
