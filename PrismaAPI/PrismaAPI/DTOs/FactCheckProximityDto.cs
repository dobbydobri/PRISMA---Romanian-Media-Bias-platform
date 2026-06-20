namespace PrismaAPI.DTOs;

public class FactCheckProximityDto
{
    public long FactCheckId { get; set; }

    public long ArticleId { get; set; }

    public string? FactCheckArticleTitle { get; set; }

    public string? FactCheckArticleUrl { get; set; }

    public string? OutletName { get; set; }

    public string Verdict { get; set; } = string.Empty;

    public string? ClaimText { get; set; }

    public double Distance { get; set; }
}
