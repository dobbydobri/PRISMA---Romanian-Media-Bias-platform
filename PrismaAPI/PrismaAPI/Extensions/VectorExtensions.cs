using System.Globalization;

namespace PrismaAPI.Extensions;

public static class VectorExtensions
{
    public static string ToVectorString(this float[] vector)
    {
        return "[" + string.Join(",", vector.Select(f => f.ToString("G9", CultureInfo.InvariantCulture))) + "]";
    }
}
