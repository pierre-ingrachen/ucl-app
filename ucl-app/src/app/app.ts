import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { ConnectiviteService } from './services/connectivite';
import { environment } from '../environments/environment';

@Component({
  selector: 'app-root',
  standalone: true,
  // 2. On l'ajoute dans le tableau des imports de l'application :
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrls: ['./app.css']
})
export class App {
  title = 'ucl-app';
  demo = environment.demo;

  constructor(public connectivite: ConnectiviteService) {}
}