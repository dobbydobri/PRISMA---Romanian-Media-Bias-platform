namespace PrismaAPI.DTOs;

public class FramingDistributionDto
{
    public string OutletName { get; set; } = string.Empty;

    public double NeutralPct { get; set; }

    public double SupportivePct { get; set; }

    public double CriticalPct { get; set; }

    public double AlarmistPct { get; set; }

    public double HumanInterestPct { get; set; }
}
