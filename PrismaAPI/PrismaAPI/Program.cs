using Microsoft.AspNetCore.Diagnostics;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Npgsql;
using Pgvector;
using PrismaAPI.Configuration;
using PrismaAPI.Data;
using PrismaAPI.Services;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

// ── CORS ──────────────────────────────────────────────────────────────────────
var allowedOrigins = builder.Configuration
    .GetSection("Cors:AllowedOrigins")
    .Get<string[]>() ?? ["http://localhost:4200"];

builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAngular", policy =>
    {
        policy.WithOrigins(allowedOrigins)
              .AllowAnyHeader()
              .AllowAnyMethod();
    });
});

// ── Controllers & JSON ────────────────────────────────────────────────────────
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
    });

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    var xmlFilename = $"{System.Reflection.Assembly.GetExecutingAssembly().GetName().Name}.xml";
    var xmlPath = Path.Combine(AppContext.BaseDirectory, xmlFilename);
    if (File.Exists(xmlPath))
    {
        options.IncludeXmlComments(xmlPath);
    }
});

// ── Database ──────────────────────────────────────────────────────────────────
builder.Services.AddDbContext<PrismaDbContext>(options =>
{
    options.UseNpgsql(
        builder.Configuration.GetConnectionString("DefaultConnection"),
        npgsqlOptions => npgsqlOptions.UseVector()
    );
    options.UseQueryTrackingBehavior(QueryTrackingBehavior.NoTracking);
});

builder.Services.AddNpgsqlDataSource(
    builder.Configuration.GetConnectionString("DefaultConnection")!,
    dataSourceBuilder => dataSourceBuilder.UseVector());

// ── Configuration ─────────────────────────────────────────────────────────────
builder.Services.Configure<SearchOptions>(
    builder.Configuration.GetSection(SearchOptions.Section));

// ── HTTP Clients ──────────────────────────────────────────────────────────────
builder.Services.AddHttpClient("QueryEmbedder", (sp, client) =>
{
    var opts = sp.GetRequiredService<IOptions<SearchOptions>>().Value;
    client.BaseAddress = new Uri(opts.EmbedderBaseUrl);
    client.Timeout = TimeSpan.FromMilliseconds(opts.EmbedderTimeoutMs);
});

builder.Services.AddHttpClient("GraphService", client =>
{
    var graphServiceUrl = builder.Configuration["GraphService:BaseUrl"]
        ?? "http://prisma-graph-service:8082";
    client.BaseAddress = new Uri(graphServiceUrl);
    client.Timeout = TimeSpan.FromSeconds(30);
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler())
  .AddTypedClient((client) => client);

// ── Application Services ──────────────────────────────────────────────────────
builder.Services.AddScoped<IOutletService, OutletService>();
builder.Services.AddScoped<IArticleService, ArticleService>();
builder.Services.AddScoped<IClusterService, ClusterService>();
builder.Services.AddScoped<IClusterRunWindowService, ClusterRunWindowService>();
builder.Services.AddScoped<IFactCheckService, FactCheckService>();
builder.Services.AddScoped<IAnalysisService, AnalysisService>();
builder.Services.AddScoped<ISearchService, SearchService>();
builder.Services.AddScoped<IConnectionsService, ConnectionsService>();
builder.Services.AddScoped<IConnectionsPathService, ConnectionsPathService>();

// ── Health Checks ─────────────────────────────────────────────────────────────
builder.Services.AddHealthChecks();

var app = builder.Build();

// ── Global Exception Handler ──────────────────────────────────────────────────
app.UseExceptionHandler(errorApp =>
{
    errorApp.Run(async context =>
    {
        context.Response.StatusCode = StatusCodes.Status500InternalServerError;
        context.Response.ContentType = "application/json";

        var feature = context.Features.Get<IExceptionHandlerFeature>();
        var logger = context.RequestServices.GetRequiredService<ILogger<Program>>();
        if (feature?.Error is not null)
        {
            logger.LogError(feature.Error, "Unhandled exception on {Method} {Path}",
                context.Request.Method, context.Request.Path);
        }

        await context.Response.WriteAsJsonAsync(new
        {
            error = "An unexpected error occurred. Please try again later."
        });
    });
});

// ── Swagger (dev only) ────────────────────────────────────────────────────────
if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI(options =>
    {
        options.SwaggerEndpoint("/swagger/v1/swagger.json", "PrismaAPI v1");
        options.RoutePrefix = "swagger";
    });
}

app.UseCors("AllowAngular");

app.MapControllers();
app.MapHealthChecks("/health");

app.Run();
