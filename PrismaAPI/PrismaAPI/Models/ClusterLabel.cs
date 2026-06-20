using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

[Table("cluster_labels")]
public class ClusterLabel
{
    [Column("cluster_run_id")]
    public int ClusterRunId { get; set; }

    [Column("cluster_id")]
    public int ClusterId { get; set; }

    [Required]
    [Column("top_tfidf_terms", TypeName = "text[]")]
    public string[] TopTfidfTerms { get; set; } = Array.Empty<string>();

    [Required]
    [Column("top_entities", TypeName = "text[]")]
    public string[] TopEntities { get; set; } = Array.Empty<string>();

    [Required]
    [Column("label_text")]
    public string LabelText { get; set; } = string.Empty;

    [Column("article_count")]
    public int ArticleCount { get; set; }

    [Column("outlet_count")]
    public int OutletCount { get; set; }

    [Column("date_from")]
    public DateOnly DateFrom { get; set; }

    [Column("date_to")]
    public DateOnly DateTo { get; set; }

    [Column("created_at")]
    public DateTime? CreatedAt { get; set; }

    [Column("parent_cluster_id")]
    public int? ParentClusterId { get; set; }

    [Column("is_event_cluster")]
    public bool IsEventCluster { get; set; }


    public ClusterRun ClusterRun { get; set; } = null!;
}
