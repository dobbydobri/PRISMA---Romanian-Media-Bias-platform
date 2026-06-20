import { Component } from '@angular/core';
import { MatTabsModule } from '@angular/material/tabs';
import { FactCheckTabComponent } from './fact-check-tab/fact-check-tab.component';

@Component({
  selector: 'app-explore',
  standalone: true,
  imports: [MatTabsModule, FactCheckTabComponent],
  templateUrl: './explore.component.html',
  styleUrl: './explore.component.scss',
})
export class ExploreComponent {}
