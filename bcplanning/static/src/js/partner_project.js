/** @odoo-module */

// document.addEventListener("DOMContentLoaded", () => {
//     document.querySelectorAll(".open_project_planning_line").forEach((btn) => {
//         btn.addEventListener("click", (ev) => {
//             ev.preventDefault();
//             const job_id = btn.dataset.job_id;
//             const job_no = btn.dataset.job_no;
//             const job_name = btn.dataset.job_name;
//             const url = `/partner/tasks?job_id=${encodeURIComponent(job_id)}&job_no=${encodeURIComponent(job_no)}&job_name=${encodeURIComponent(job_name)}`;
//             window.location.href = url;
//         });
//     });
// });

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".open_project_planning_line").forEach((btn) => {
        btn.addEventListener("click", (ev) => {
            ev.preventDefault();
            const td = btn.closest('td');
            const projectIdSpan = td.querySelector('.data_project_id');
            const projectNoSpan = td.querySelector('.data_project_no');
            const projectNameSpan = td.querySelector('.data_project_desc');
            
            // Check if spans exist before reading
            if (projectIdSpan) {
                const job_id = projectIdSpan.textContent.trim();
                const job_no = projectNoSpan.textContent.trim();
                const job_name = projectNameSpan.textContent.trim();
                const url = `/partner/tasks?job_id=${encodeURIComponent(job_id)}&job_no=${encodeURIComponent(job_no)}&job_name=${encodeURIComponent(job_name)}`;
                window.location.href = url;
            } else {
                alert("Project data not found!");
            }
        });
    });
});