/// <reference types="vite/client" />

// The partial Plotly bundles have the API (and types) of the full one.
declare module 'plotly.js-basic-dist-min' {
  import Plotly from 'plotly.js-dist-min'
  export default Plotly
}
declare module 'plotly.js-cartesian-dist-min' {
  import Plotly from 'plotly.js-dist-min'
  export default Plotly
}
declare module 'plotly.js-gl2d-dist-min' {
  import Plotly from 'plotly.js-dist-min'
  export default Plotly
}
declare module 'plotly.js-gl3d-dist-min' {
  import Plotly from 'plotly.js-dist-min'
  export default Plotly
}
