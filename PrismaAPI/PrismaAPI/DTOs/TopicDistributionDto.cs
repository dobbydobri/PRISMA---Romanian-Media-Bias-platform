namespace PrismaAPI.DTOs;

public class TopicDistributionDto
{
    public string OutletName { get; set; } = string.Empty;

    public double PoliticsPct { get; set; }

    public double EconomyPct { get; set; }

    public double ForeignAffairsPct { get; set; }

    public double JusticePct { get; set; }

    public double HealthPct { get; set; }

    public double SportsPct { get; set; }

    public double CulturePct { get; set; }

    public double SocialPct { get; set; }

    public double EnvironmentPct { get; set; }

    public double TechnologyPct { get; set; }
}
