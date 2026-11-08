import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ParisManuelsService, PariManuel } from '../services/paris-manuels';

@Component({
  selector: 'app-mes-paris',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './mes-paris.html',
  styleUrl: './mes-paris.css'
})
export class MesParis {
  paris: PariManuel[] = [];

  constructor(private service: ParisManuelsService) {
    this.paris = this.service.liste();
  }

  equipeChoisie(p: PariManuel): string {
    return p.equipe === 'home' ? p.domicile : p.equipe === 'away' ? p.exterieur : '';
  }

  supprimer(p: PariManuel): void {
    if (!confirm(`Supprimer les notes sur ${p.domicile} – ${p.exterieur} ?`)) return;
    this.service.supprimer(p.idMatch);
    this.paris = this.service.liste();
  }
}
