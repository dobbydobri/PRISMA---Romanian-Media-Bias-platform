using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("factcheck_cluster_map")]
public class FactCheckClusterMap
{
    [Column("factcheck_id")]
    public long FactcheckId { get; set; }

    [Column("article_id")]
    public long ArticleId { get; set; }

    [Column("cluster_run_id")]
    public int ClusterRunId { get; set; }

    [Column("cluster_id")]
    public int ClusterId { get; set; }

    [Column("sub_cluster_id")]
    public int? SubClusterId { get; set; }

    [Column("similarity")]
    public double? Similarity { get; set; }

    [Column("sub_similarity")]
    public double? SubSimilarity { get; set; }
}
