document.getElementById('upload-form').onchange = function(event) {
    var image = document.getElementById('displayed-image');
    image.src = URL.createObjectURL(event.target.files[0]);
    image.hidden = false;
};

form.onsubmit = function(event) {
    event.preventDefault();
    const formData = new FormData(form);
    fetch('/upload', {
        method: 'POST',
        body: formData,
    }).then(response => response.blob())
      .then(blob => {
        const imageUrl = URL.createObjectURL(blob);
        const image = new Image();
        image.onload = function() {
            // 캔버스 크기를 이미지 크기에 맞추기
            imageCanvas.width = image.width;
            imageCanvas.height = image.height;
            // 이미지를 캔버스에 그리기
            ctx.drawImage(image, 0, 0, image.width, image.height);
        };
        image.src = imageUrl;
    });
};