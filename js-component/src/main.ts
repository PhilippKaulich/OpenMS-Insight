import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

// Vuetify
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import { createVuetify } from 'vuetify'

const app = createApp(App)

app.use(createPinia())

app.use(
  // Components and directives are imported where a view uses them
  // (vite-plugin-vuetify), so each view loads only the Vuetify code and
  // styles it needs
  createVuetify()
)

app.mount('#app')
