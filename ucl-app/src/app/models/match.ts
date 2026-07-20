export interface Match {
  idEvent: string;
  strHomeTeam: string;
  strAwayTeam: string;
  dateEvent: string;
  strTime: string;
  strHomeTeamBadge: string;
  strAwayTeamBadge: string;
  intRound: string;
  localDateTime?: Date;
}

export interface ApiResponse {
  events: Match[];
}