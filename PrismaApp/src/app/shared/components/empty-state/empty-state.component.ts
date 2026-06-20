import { Component, input, output } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [MatIconModule, MatButtonModule],
  templateUrl: './empty-state.component.html',
  styleUrl: './empty-state.component.scss',
})
export class EmptyStateComponent {
  icon = input<string>('inbox');
  title = input<string>('Niciun rezultat');
  description = input<string>('');
  
  showRetry = input<boolean>(false);
  retry = output<void>();

  onRetry(): void {
    this.retry.emit();
  }
}
