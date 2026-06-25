import { Component } from '@angular/core';
import { MatTabsModule } from '@angular/material/tabs';
import { FactCheckTabComponent } from './fact-check-tab/fact-check-tab.component';
import { TopicTabComponent } from './topic-tab/topic-tab.component';

@Component({
  selector: 'app-explore',
  standalone: true,
  imports: [MatTabsModule, FactCheckTabComponent, TopicTabComponent],
  templateUrl: './explore.component.html',
  styleUrl: './explore.component.scss',
})
export class ExploreComponent {}
