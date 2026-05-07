"""GraphQL strings for the WCL queries we use.

Kept in one file so they can be reviewed/lint-checked together. Each query
is intentionally minimal (only the fields we map to our DB) to keep response
size low.
"""
from __future__ import annotations

REPORT_OVERVIEW = """
query ReportOverview($code: String!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      zone { id name }
      region { compactName }
      gameVersion
      fights(killType: All) {
        id
        encounterID
        name
        difficulty
        keystoneLevel
        kill
        bossPercentage
        startTime
        endTime
      }
    }
  }
}
"""

REPORT_TABLES = """
query ReportTable(
  $code: String!,
  $fightIDs: [Int]!,
  $dataType: TableDataType!
) {
  reportData {
    report(code: $code) {
      table(fightIDs: $fightIDs, dataType: $dataType)
    }
  }
}
"""

REPORT_PLAYER_DETAILS = """
query ReportPlayerDetails($code: String!, $fightIDs: [Int]!) {
  reportData {
    report(code: $code) {
      playerDetails(fightIDs: $fightIDs)
    }
  }
}
"""

REPORT_CASTS = """
query ReportCasts(
  $code: String!,
  $fightIDs: [Int]!,
  $sourceID: Int!
) {
  reportData {
    report(code: $code) {
      table(fightIDs: $fightIDs, dataType: Casts, sourceID: $sourceID)
    }
  }
}
"""

# Top rankings for a given encounter+spec+metric on the world leaderboard.
# `page` lets us paginate; we typically only fetch page 1 (top 25-50).
ENCOUNTER_RANKINGS = """
query EncounterRankings(
  $encounterID: Int!,
  $specName: String,
  $className: String,
  $metric: CharacterRankingMetricType!,
  $page: Int!,
  $partition: Int
) {
  worldData {
    encounter(id: $encounterID) {
      id
      name
      characterRankings(
        specName: $specName,
        className: $className,
        metric: $metric,
        page: $page,
        partition: $partition
      )
    }
  }
}
"""
