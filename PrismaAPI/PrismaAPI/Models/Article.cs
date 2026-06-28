using System.ComponentModel.DataAnnotations;
using Pgvector;

namespace PrismaAPI.Models;

/// <summary>
/// Represents a scraped news article.
/// Column-to-property mapping is configured exclusively via Fluent API in <see cref="PrismaAPI.Data.PrismaDbContext"/>.
/// Only validation constraints ([Required], [MaxLength]) are kept here.
/// </summary>
public class Article
{
    public long Id { get; set; }

    public int OutletId { get; set; }

    public string? Url { get; set; }

    public string? UrlHash { get; set; }

    [Required]
    public string Title { get; set; } = string.Empty;

    public string? ContentText { get; set; }

    public string[]? Authors { get; set; }

    public DateTime? PublishedAt { get; set; }

    public long? QueueId { get; set; }


    public Vector? Embedding { get; set; }

    public DateTime? EmbeddedAt { get; set; }

    public string? EmbeddingModel { get; set; }

    public string? EmbeddingVersion { get; set; }


    public int? ClusterRunId { get; set; }

    public int? ClusterId { get; set; }

    public int? SubClusterId { get; set; }


    public double? ScoreSensationalism { get; set; }

    public double? ScoreCitationQuality { get; set; }

    public double? ScoreRhetoricIntensity { get; set; }

    public string? DiscourseRegisters { get; set; }


    public double? LlmCoalition { get; set; }

    public double? LlmEuAxis { get; set; }

    [MaxLength(20)]
    public string? LlmFraming { get; set; }

    [MaxLength(30)]
    public string? LlmTopic { get; set; }

    public DateTime? LlmScoredAt { get; set; }

    public string? LlmPromptVersion { get; set; }

    public string? LlmGovStance { get; set; }

    public string? LlmSovereignism { get; set; }

    public string? LlmConfidence { get; set; }


    public string? TfGovStance { get; set; }

    public string? TfGovStanceProb { get; set; }

    public float? TfGovStanceConf { get; set; }

    public string? TfFraming { get; set; }

    public string? TfFramingProb { get; set; }

    public float? TfFramingConf { get; set; }

    public string? TfSovereignism { get; set; }

    public string? TfSovereignismProb { get; set; }

    public float? TfSovereignismConf { get; set; }

    public string? TfTopic { get; set; }

    public string? TfTopicProb { get; set; }

    public float? TfTopicConf { get; set; }


    public bool? IsExcluded { get; set; }

    public bool? IsTemplated { get; set; }

    public NpgsqlTypes.NpgsqlTsVector? Fts { get; set; }


    // Navigation properties
    public Outlet Outlet { get; set; } = null!;

    public ICollection<ArticleEntity> ArticleEntities { get; set; } = new List<ArticleEntity>();

    public ClusterRun? ClusterRun { get; set; }

    public FactCheck? FactCheck { get; set; }
}
