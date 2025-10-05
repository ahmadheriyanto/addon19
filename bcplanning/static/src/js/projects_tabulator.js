odoo.define('bcplanning.projects_tabulator', [], function(require){
    'use strict';

    $(document).ready(function () {
        // Initialize Tabulator grid
        var table = new Tabulator("#projects-table", {
            ajaxURL: "/portal/projects",
            layout:"fitColumns",
            columns:[
                {title:"Job No", field:"job_no", editor:"input"},
                {title:"Job Desc", field:"job_desc", editor:"input"},
                {title:"Partner", field:"partner_name"},
                {title:"Actions", field:"id", formatter:function(cell, formatterParams){
                    return "<button class='edit-btn btn btn-sm btn-info'>Tasks & Resources</button> ";
                        //   + "<button class='delete-btn btn btn-sm btn-danger'>Delete</button>";
                }},
            ],
            cellEdited: function(cell) {
                var data = cell.getRow().getData();
                $.ajax({
                    url: "/portal/projects/update",
                    type: "POST",
                    contentType: "application/json",
                    data: JSON.stringify(data),
                    success: function(resp) {
                        table.replaceData();
                    }
                });
            }
        });

        // // Add new record
        // $('#add-project').on('click', function(){
        //     Swal.fire({
        //         title: 'Create Project',
        //         html:
        //           '<input id="job_no" class="swal2-input" placeholder="Job No">' +
        //           '<input id="job_desc" class="swal2-input" placeholder="Job Desc">',
        //         focusConfirm: false,
        //         preConfirm: () => {
        //             return {
        //                 job_no: $('#job_no').val(),
        //                 job_desc: $('#job_desc').val(),
        //             }
        //         }
        //     }).then((result) => {
        //         if (result.isConfirmed) {
        //             $.ajax({
        //                 url: "/portal/projects/create",
        //                 type: "POST",
        //                 contentType: "application/json",
        //                 data: JSON.stringify(result.value),
        //                 success: function(resp) {
        //                     table.replaceData();
        //                 }
        //             });
        //         }
        //     });
        // });

        // Edit and delete events
        $("#projects-table").on("click", ".edit-btn", function(e){
            var row = table.getRowFromElement(e.target);
            var data = row.getData();
            Swal.fire({
                title: 'Edit Project',
                html:
                  `<input id="job_no" class="swal2-input" value="${data.job_no}">` +
                  `<input id="job_desc" class="swal2-input" value="${data.job_desc}">`,
                focusConfirm: false,
                preConfirm: () => {
                    return {
                        id: data.id,
                        job_no: $('#job_no').val(),
                        job_desc: $('#job_desc').val(),
                    }
                }
            }).then((result) => {
                if (result.isConfirmed) {
                    $.ajax({
                        url: "/portal/projects/update",
                        type: "POST",
                        contentType: "application/json",
                        data: JSON.stringify(result.value),
                        success: function(resp) {
                            table.replaceData();
                        }
                    });
                }
            });
        });

        // $("#projects-table").on("click", ".delete-btn", function(e){
        //     var row = table.getRowFromElement(e.target);
        //     var data = row.getData();
        //     Swal.fire({
        //         title: 'Delete Project',
        //         text: "Are you sure?",
        //         showCancelButton: true,
        //         confirmButtonText: 'Delete'
        //     }).then((result) => {
        //         if (result.isConfirmed) {
        //             $.ajax({
        //                 url: "/portal/projects/delete",
        //                 type: "POST",
        //                 contentType: "application/json",
        //                 data: JSON.stringify({id: data.id}),
        //                 success: function(resp) {
        //                     table.replaceData();
        //                 }
        //             });
        //         }
        //     });
        // });

    });
});