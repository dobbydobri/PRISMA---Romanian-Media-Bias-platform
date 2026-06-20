namespace PrismaAPI.DTOs;

public class FactCheckDto
{
    public long Id { get; set; }

    public long ArticleId { get; set; }

    public string? ArticleTitle { get; set; }

    public string? OutletName { get; set; }

    public string Verdict { get; set; } = string.Empty;

    public string VerdictType { get; set; } = string.Empty;

    public string? ClaimText { get; set; }

    public string? RawVerdict { get; set; }

    public DateTime? PublishedAt { get; set; }

    public int? LinkedClusterId { get; set; }

    public string? LinkedClusterLabel { get; set; }
}
