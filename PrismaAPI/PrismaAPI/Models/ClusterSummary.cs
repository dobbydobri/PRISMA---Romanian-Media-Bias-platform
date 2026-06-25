using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("cluster_summaries")]
public class ClusterSummary
{
    [Key]
    [Column("id")]
    public long Id { get; set; }

    [Column("scope")]
    public string? Scope { get; set; }

    [Column("cluster_run_id")]
    public int ClusterRunId { get; set; }

    [Column("cluster_id")]
    public int ClusterId { get; set; }

    [Column("summary_text")]
    public string? SummaryText { get; set; }

    [Column("key_points", TypeName = "jsonb")]
    public string? KeyPoints { get; set; }

    [Column("source_article_ids")]
    public int[]? SourceArticleIds { get; set; }

    [Column("model")]
    public string? Model { get; set; }

    [Column("prompt_version")]
    public string? PromptVersion { get; set; }

    [Column("mean_pairwise_cosine")]
    public float? MeanPairwiseCosine { get; set; }

    [Column("generation_ms")]
    public int? GenerationMs { get; set; }

    [Column("generated_at")]
    public DateTime? GeneratedAt { get; set; }

    [Column("cluster_title")]
    public string? ClusterTitle { get; set; }


    public ClusterRun? ClusterRun { get; set; }
}
