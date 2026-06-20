namespace PrismaAPI.DTOs;

public class EntityConnectionDto
{
    public string EntityName { get; set; } = string.Empty;

    public string EntityLabel { get; set; } = string.Empty;

    public int CoMentionCount { get; set; }

    public double WeightPmi { get; set; }
}

public class EntityPathDto
{
    public List<string> Path { get; set; } = new();

    public int TotalDistance { get; set; }
}

public class EntityArticleDto
{
    public long ArticleId { get; set; }

    public string Title { get; set; } = string.Empty;

    public string? OutletName { get; set; }

    public DateTime? PublishedAt { get; set; }
}
