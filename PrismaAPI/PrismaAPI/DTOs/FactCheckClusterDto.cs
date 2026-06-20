namespace PrismaAPI.DTOs;

public class FactCheckClusterDto
{
    public long FactcheckId { get; set; }

    public long ArticleId { get; set; }

    public string? ArticleTitle { get; set; }

    public string? OutletName { get; set; }

    public string? Verdict { get; set; }

    public string? VerdictType { get; set; }

    public string? ClaimText { get; set; }

    public int ClusterRunId { get; set; }

    public int ClusterId { get; set; }

    public int? SubClusterId { get; set; }

    public double? Similarity { get; set; }

    public double? SubSimilarity { get; set; }
}
