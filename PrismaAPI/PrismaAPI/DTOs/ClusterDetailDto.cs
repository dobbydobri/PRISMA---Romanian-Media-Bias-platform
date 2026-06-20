namespace PrismaAPI.DTOs;

public class ClusterDetailDto
{
    public int ClusterId { get; set; }

    public int RunId { get; set; }

    public string LabelText { get; set; } = string.Empty;

    public string[] TopTfidfTerms { get; set; } = Array.Empty<string>();

    public string[] TopEntities { get; set; } = Array.Empty<string>();

    public int ArticleCount { get; set; }

    public int OutletCount { get; set; }

    public DateOnly DateFrom { get; set; }

    public DateOnly DateTo { get; set; }

    public bool IsEventCluster { get; set; }

    public int? ParentClusterId { get; set; }

    public Dictionary<string, List<ArticleListDto>> ArticlesByOutlet { get; set; } = new();

    public List<FactCheckDto> LinkedFactChecks { get; set; } = new();
}
