using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using Pgvector;

namespace PrismaAPI.Models;

[Table("articles")]
public class Article
{
    [Key]
    [Column("id")]
    public long Id { get; set; }

    [Column("outlet_id")]
    public int OutletId { get; set; }

    [Column("url")]
    public string? Url { get; set; }

    [Column("url_hash", TypeName = "char(32)")]
    public string? UrlHash { get; set; }

    [Required]
    [Column("title")]
    public string Title { get; set; } = string.Empty;

    [Column("content_text")]
    public string? ContentText { get; set; }

    [Column("authors", TypeName = "text[]")]
    public string[]? Authors { get; set; }

    [Column("published_at")]
    public DateTime? PublishedAt { get; set; }

    [Column("queue_id")]
    public long? QueueId { get; set; }


    [Column("embedding", TypeName = "vector(1024)")]
    public Vector? Embedding { get; set; }

    [Column("embedded_at")]
    public DateTime? EmbeddedAt { get; set; }

    [Column("embedding_model")]
    public string? EmbeddingModel { get; set; }

    [Column("embedding_version")]
    public string? EmbeddingVersion { get; set; }


    [Column("cluster_run_id")]
    public int? ClusterRunId { get; set; }

    [Column("cluster_id")]
    public int? ClusterId { get; set; }

    [Column("sub_cluster_id")]
    public int? SubClusterId { get; set; }


    [Column("score_sensationalism")]
    public double? ScoreSensationalism { get; set; }

    [Column("score_citation_quality")]
    public double? ScoreCitationQuality { get; set; }

    [Column("score_rhetoric_intensity")]
    public double? ScoreRhetoricIntensity { get; set; }

    [Column("discourse_registers", TypeName = "jsonb")]
    public string? DiscourseRegisters { get; set; }


    [Column("llm_coalition")]
    public double? LlmCoalition { get; set; }

    [Column("llm_eu_axis")]
    public double? LlmEuAxis { get; set; }

    [MaxLength(20)]
    [Column("llm_framing")]
    public string? LlmFraming { get; set; }

    [MaxLength(30)]
    [Column("llm_topic")]
    public string? LlmTopic { get; set; }

    [Column("llm_scored_at")]
    public DateTime? LlmScoredAt { get; set; }



    public Outlet Outlet { get; set; } = null!;

    public ICollection<ArticleEntity> ArticleEntities { get; set; } = new List<ArticleEntity>();




    public ClusterRun? ClusterRun { get; set; }

    public FactCheck? FactCheck { get; set; }

    [Column("is_excluded")]
    public bool? IsExcluded { get; set; }

    [Column("fts", TypeName = "tsvector")]
    public NpgsqlTypes.NpgsqlTsVector? Fts { get; set; }

    [Column("is_templated")]
    public bool? IsTemplated { get; set; }

    [Column("llm_prompt_version")]
    public string? LlmPromptVersion { get; set; }

    [Column("llm_gov_stance")]
    public string? LlmGovStance { get; set; }

    [Column("llm_sovereignism")]
    public string? LlmSovereignism { get; set; }

    [Column("llm_confidence")]
    public string? LlmConfidence { get; set; }

    [Column("tf_gov_stance")]
    public string? TfGovStance { get; set; }

    [Column("tf_gov_stance_prob", TypeName = "jsonb")]
    public string? TfGovStanceProb { get; set; }

    [Column("tf_gov_stance_conf")]
    public float? TfGovStanceConf { get; set; }

    [Column("tf_framing")]
    public string? TfFraming { get; set; }

    [Column("tf_framing_prob", TypeName = "jsonb")]
    public string? TfFramingProb { get; set; }

    [Column("tf_framing_conf")]
    public float? TfFramingConf { get; set; }

    [Column("tf_sovereignism")]
    public string? TfSovereignism { get; set; }

    [Column("tf_sovereignism_prob", TypeName = "jsonb")]
    public string? TfSovereignismProb { get; set; }

    [Column("tf_sovereignism_conf")]
    public float? TfSovereignismConf { get; set; }

    [Column("tf_topic")]
    public string? TfTopic { get; set; }

    [Column("tf_topic_prob", TypeName = "jsonb")]
    public string? TfTopicProb { get; set; }

    [Column("tf_topic_conf")]
    public float? TfTopicConf { get; set; }
}
