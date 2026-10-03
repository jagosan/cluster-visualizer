/**
 * AuthModal Component
 * TASK-CV-806 / SPEC-07 §5.1
 *
 * Provides a modal dialog for entering Kubernetes ServiceAccount Bearer Tokens.
 * Tokens are stored in browser sessionStorage for the current tab only.
 */

export class AuthModal {
  private overlay: HTMLElement | null = null;
  private onConnectCallback: ((token: string) => void) | null = null;

  constructor() {
    // Initialize with null state; modal is created on open()
  }

  /**
   * Opens the authentication modal.
   * @param clusterName - The name of the cluster to connect to.
   * @param clusterUrl - The URL of the cluster API server.
   * @param onConnect - Callback invoked with the entered token when the user clicks Connect.
   */
  open(clusterName: string, clusterUrl: string, onConnect: (token: string) => void): void {
    // Close any existing modal first
    this.close();

    this.onConnectCallback = onConnect;

    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'auth-modal-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
    overlay.style.display = 'flex';
    overlay.style.justifyContent = 'center';
    overlay.style.alignItems = 'center';
    overlay.style.zIndex = '10000';

    // Create modal container
    const modal = document.createElement('div');
    modal.className = 'auth-modal';
    modal.style.backgroundColor = '#ffffff';
    modal.style.borderRadius = '8px';
    modal.style.padding = '24px';
    modal.style.width = '500px';
    modal.style.maxWidth = '90%';
    modal.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
    modal.style.fontFamily = 'system-ui, -apple-system, sans-serif';

    // Title
    const title = document.createElement('h2');
    title.textContent = `Connect to ${clusterName}`;
    title.style.marginTop = '0';
    title.style.marginBottom = '16px';
    title.style.fontSize = '18px';
    title.style.color = '#1a1a1a';
    modal.appendChild(title);

    // Security explanation
    const securityNote = document.createElement('p');
    securityNote.textContent =
      'Tokens are stored in browser sessionStorage for this tab only, never persisted to disk or localStorage.';
    securityNote.style.fontSize = '12px';
    securityNote.style.color = '#666666';
    securityNote.style.marginBottom = '16px';
    securityNote.style.lineHeight = '1.4';
    modal.appendChild(securityNote);

    // Form
    const form = document.createElement('form');
    form.className = 'auth-modal-form';
    form.style.display = 'flex';
    form.style.flexDirection = 'column';
    form.style.gap = '12px';

    // Cluster URL field
    const urlLabel = document.createElement('label');
    urlLabel.textContent = 'Cluster URL';
    urlLabel.style.fontSize = '14px';
    urlLabel.style.fontWeight = '500';
    urlLabel.style.color = '#333333';
    urlLabel.style.display = 'block';
    urlLabel.style.marginBottom = '4px';

    const urlInput = document.createElement('input');
    urlInput.type = 'text';
    urlInput.value = clusterUrl;
    urlInput.readOnly = true;
    urlInput.style.padding = '8px 12px';
    urlInput.style.border = '1px solid #cccccc';
    urlInput.style.borderRadius = '4px';
    urlInput.style.fontSize = '14px';
    urlInput.style.backgroundColor = '#f5f5f5';
    urlInput.style.color = '#666666';
    urlInput.style.width = '100%';
    urlInput.style.boxSizing = 'border-box';

    const urlField = document.createElement('div');
    urlField.appendChild(urlLabel);
    urlField.appendChild(urlInput);
    form.appendChild(urlField);

    // Token field
    const tokenLabel = document.createElement('label');
    tokenLabel.textContent = 'ServiceAccount Bearer Token';
    tokenLabel.style.fontSize = '14px';
    tokenLabel.style.fontWeight = '500';
    tokenLabel.style.color = '#333333';
    tokenLabel.style.display = 'block';
    tokenLabel.style.marginBottom = '4px';

    const tokenInput = document.createElement('textarea');
    tokenInput.placeholder = 'Paste your Kubernetes ServiceAccount Bearer Token here...';
    tokenInput.rows = 6;
    tokenInput.style.padding = '8px 12px';
    tokenInput.style.border = '1px solid #cccccc';
    tokenInput.style.borderRadius = '4px';
    tokenInput.style.fontSize = '14px';
    tokenInput.style.fontFamily = 'monospace';
    tokenInput.style.resize = 'vertical';
    tokenInput.style.width = '100%';
    tokenInput.style.boxSizing = 'border-box';

    const tokenField = document.createElement('div');
    tokenField.appendChild(tokenLabel);
    tokenField.appendChild(tokenInput);
    form.appendChild(tokenField);

    // Buttons container
    const buttonsContainer = document.createElement('div');
    buttonsContainer.style.display = 'flex';
    buttonsContainer.style.justifyContent = 'flex-end';
    buttonsContainer.style.gap = '8px';
    buttonsContainer.style.marginTop = '8px';

    // Cancel button
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.textContent = 'Cancel';
    cancelButton.style.padding = '8px 16px';
    cancelButton.style.border = '1px solid #cccccc';
    cancelButton.style.borderRadius = '4px';
    cancelButton.style.backgroundColor = '#ffffff';
    cancelButton.style.color = '#333333';
    cancelButton.style.fontSize = '14px';
    cancelButton.style.cursor = 'pointer';
    cancelButton.addEventListener('click', () => {
      this.close();
    });

    // Connect button
    const connectButton = document.createElement('button');
    connectButton.type = 'submit';
    connectButton.textContent = 'Connect';
    connectButton.style.padding = '8px 16px';
    connectButton.style.border = 'none';
    connectButton.style.borderRadius = '4px';
    connectButton.style.backgroundColor = '#007acc';
    connectButton.style.color = '#ffffff';
    connectButton.style.fontSize = '14px';
    connectButton.style.cursor = 'pointer';
    connectButton.style.fontWeight = '500';

    buttonsContainer.appendChild(cancelButton);
    buttonsContainer.appendChild(connectButton);
    form.appendChild(buttonsContainer);

    // Handle form submission
    form.addEventListener('submit', (event: Event) => {
      event.preventDefault();
      const token = tokenInput.value.trim();
      if (token.length === 0) {
        tokenInput.focus();
        return;
      }
      if (this.onConnectCallback !== null) {
        this.onConnectCallback(token);
      }
      this.close();
    });

    modal.appendChild(form);
    overlay.appendChild(modal);

    // Close on overlay click (outside modal)
    overlay.addEventListener('click', (event: MouseEvent) => {
      if (event.target === overlay) {
        this.close();
      }
    });

    // Close on Escape key
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        this.close();
        document.removeEventListener('keydown', handleKeyDown);
      }
    };
    document.addEventListener('keydown', handleKeyDown);

    // Store references
    this.overlay = overlay;

    // Append to DOM
    document.body.appendChild(overlay);

    // Focus token input
    tokenInput.focus();
  }

  /**
   * Closes and removes the authentication modal.
   */
  close(): void {
    if (this.overlay !== null) {
      document.body.removeChild(this.overlay);
      this.overlay = null;
    }
    this.onConnectCallback = null;
  }
}
