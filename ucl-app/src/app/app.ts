import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { ConnectiviteService } from './services/connectivite';

@Component({
  selector: 'app-root',
  standalone: true,
  // 2. On l'ajoute dans le tableau des imports de l'application :
  imports: [CommonModule, RouterOutlet],
  templateUrl: './app.html',
  styleUrls: ['./app.css']
})
export class App {
  title = 'ucl-app';

  constructor(public connectivite: ConnectiviteService) {}
}