namespace PrismaAPI.DTOs;

public class LlmVsXgboostDto
{
    public long ArticleId { get; set; }

    public string Title { get; set; } = string.Empty;

    public double? LlmCoalition { get; set; }

    public double? LlmEuAxis { get; set; }

    public double? TfGovStanceConf { get; set; }

    public double? TfSovereignismConf { get; set; }

    public string? LlmFraming { get; set; }

    public string? TfTopic { get; set; }
}
