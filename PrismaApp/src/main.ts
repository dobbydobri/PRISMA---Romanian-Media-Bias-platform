import { bootstrapApplication } from '@angular/platform-browser';
import { registerLocaleData } from '@angular/common';
import localeRo from '@angular/common/locales/ro';
import { appConfig } from './app/app.config';
import { App } from './app/app';

registerLocaleData(localeRo, 'ro');

bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));
