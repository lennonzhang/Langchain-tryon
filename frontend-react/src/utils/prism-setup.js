/**
 * Prism.js setup — imports core + common languages.
 * Import this file once (e.g. in App.jsx) to enable syntax highlighting
 * in RichBlock code blocks via window.Prism.
 */
import Prism from "prismjs";

// Markup must load before JSX/TSX
import "prismjs/components/prism-markup";
import "prismjs/components/prism-css";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-python";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-java";
import "prismjs/components/prism-c";
import "prismjs/components/prism-cpp";
import "prismjs/components/prism-go";
import "prismjs/components/prism-rust";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";

// Disable Prism's auto-highlighting (we call highlightElement manually)
Prism.manual = true;

export default Prism;
