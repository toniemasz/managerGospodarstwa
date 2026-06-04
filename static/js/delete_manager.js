/**
 * Universal Delete Manager
 * Handles all delete confirmations with a global modal
 * Integrates with forms that have class 'delete-form'
 */

document.addEventListener('DOMContentLoaded', function() {
    const deleteModal = document.getElementById('deleteModal');
    const cancelBtn = document.getElementById('cancelDeleteBtn');
    const confirmBtn = document.getElementById('confirmDeleteBtn');
    const deleteItemNameSpan = document.getElementById('deleteItemName');
    
    let pendingDeleteForm = null;

    // Handle all delete form submissions
    document.addEventListener('submit', function(e) {
        const form = e.target;
        
        // Check if this is a delete form
        if (form.classList.contains('delete-form')) {
            e.preventDefault();
            
            // Get the item name from data attribute
            const itemName = form.dataset.deleteItem || 'element';
            
            // Show modal with item name
            pendingDeleteForm = form;
            deleteItemNameSpan.textContent = itemName;
            deleteModal.classList.remove('hidden');
        }
    });

    // Cancel delete
    cancelBtn.addEventListener('click', function() {
        deleteModal.classList.add('hidden');
        pendingDeleteForm = null;
    });

    // Confirm delete
    confirmBtn.addEventListener('click', function() {
        if (pendingDeleteForm) {
            deleteModal.classList.add('hidden');
            // Submit the form programmatically
            pendingDeleteForm.submit();
        }
    });

    // Close modal when clicking outside
    deleteModal.addEventListener('click', function(e) {
        if (e.target === deleteModal) {
            deleteModal.classList.add('hidden');
            pendingDeleteForm = null;
        }
    });

    // Close modal with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !deleteModal.classList.contains('hidden')) {
            deleteModal.classList.add('hidden');
            pendingDeleteForm = null;
        }
    });
});
