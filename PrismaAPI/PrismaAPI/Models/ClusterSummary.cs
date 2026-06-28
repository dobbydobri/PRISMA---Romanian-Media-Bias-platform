using System.ComponentModel.DataAnnotations.Schema;

namespace PrismaAPI.Models;

/// <summary>
/// Represents an LLM-generated narrative summary for a cluster or event.
/// Column-to-property mapping is configured exclusively via Fluent API in <see cref="PrismaAPI.Data.PrismaDbContext"/>.
/// </summary>
public class ClusterSummary
{
    public long Id { get; set; }

    public string? Scope { get; set; }

    public int ClusterRunId { get; set; }

    public int ClusterId { get; set; }

    public string? SummaryText { get; set; }

    /// <summary>
    /// Key bullet points stored as a JSON array in the database.
    /// EF Core maps this via HasConversion&lt;List&lt;string&gt;&gt; in OnModelCreating.
    /// </summary>
    public List<string>? KeyPoints { get; set; }

    public int[]? SourceArticleIds { get; set; }

    public string? Model { get; set; }

    public string? PromptVersion { get; set; }

    public float? MeanPairwiseCosine { get; set; }

    public int? GenerationMs { get; set; }

    public DateTime? GeneratedAt { get; set; }

    public string? ClusterTitle { get; set; }

    public ClusterRun? ClusterRun { get; set; }
}
