namespace PrismaAPI.DTOs;

// Autocomplete
public record EntitySuggestionDto(
    string Name,
    string Label,
    int ArticleCount,
    int NodeDegree
);

// Direct connection
public record DirectConnectionDto(
    int ArticleCount,
    List<ConnectionArticleDto> Articles
);

// Indirect path
public record PathEdgeDto(
    string From,
    string To,
    double Pmi,
    int Raw,
    List<ConnectionArticleDto> Articles  // supporting articles for this edge
);

public record IndirectPathDto(
    List<string> Nodes,
    double Score,
    int Hops,
    List<PathEdgeDto> Edges
);

// Article used as evidence for a connection
public record ConnectionArticleDto(
    long Id,
    string Title,
    string Url,
    string Outlet,
    DateTimeOffset? PublishedAt
);

// Full path response
public record EntityPathResponseDto(
    string EntityA,
    string EntityB,
    DirectConnectionDto? Direct,
    List<IndirectPathDto> Indirect
);
