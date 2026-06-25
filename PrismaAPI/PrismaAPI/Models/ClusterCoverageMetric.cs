using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("cluster_coverage_metrics")]
public class ClusterCoverageMetric
{
    [Column("cluster_run_id")]
    public int ClusterRunId { get; set; }

    [Column("cluster_id")]
    public int ClusterId { get; set; }

    [Column("article_count")]
    public int? ArticleCount { get; set; }

    [Column("outlet_count")]
    public int? OutletCount { get; set; }

    [Column("outlet_type_count")]
    public int? OutletTypeCount { get; set; }

    [Column("popularity_score")]
    public float? PopularityScore { get; set; }

    [Column("gap_score")]
    public float? GapScore { get; set; }

    [Column("category")]
    public string? Category { get; set; }

    [Column("covering_outlets", TypeName = "jsonb")]
    public string? CoveringOutlets { get; set; }

    [Column("missing_outlets", TypeName = "jsonb")]
    public string? MissingOutlets { get; set; }

    [Column("computed_at")]
    public DateTime? ComputedAt { get; set; }
}
