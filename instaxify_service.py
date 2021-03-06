from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import subprocess
import base64
import cgi
# Determine uploaded file mime-type
import magic
import io

# For ICC profile conversion
from PIL import Image
from PIL import ImageCms
from PIL import ImageFilter

# For path splitting
from os.path import splitext

class InstaxConvert(object):
    def __init__(self):
        input_profile = "calibration/sRGB.icm"
        proof_profile = "calibration/instax-sp1_00.icc"
        self.max_dim = 640
        self.quality = 100

        # Best visually from experimentation
        self.r = 0.6
        self.p = 200
        self.t = 0

        # Create ICC transform, save for reuse
        self.proof_xform = ImageCms.buildTransform(proof_profile, input_profile, "RGB", "RGB")

    def convert(self, img_byte):
        payload_bytes = io.BytesIO(img_byte)
        im_orig = Image.open(payload_bytes).convert('RGB')

        # Calculate resized image size, scale by longest edge
        resize_ratio = max(im_orig.size)/self.max_dim
        resize_dim = (int(d / resize_ratio) for d in im_orig.size)

        # Resize
        im = im_orig.resize(resize_dim, resample=Image.LANCZOS)
        # Free memory from original image read
        del im_orig
        payload_bytes.close()

        # Save to byte array for output; this is freed by the caller
        output_img = io.BytesIO()
        im_sharpen = im.filter(ImageFilter.UnsharpMask(radius=self.r, percent=self.p, threshold=self.t))
        del im
        
        # Convert ICC profile
        ImageCms.applyTransform(im_sharpen, self.proof_xform, inPlace=True)

        im_sharpen.save(output_img, format='JPEG', quality=self.quality)
        del im_sharpen

        return output_img


# Hold onto this since we create a global xform profile
print("Creating ICC conversion profile...")
instax = InstaxConvert()


class InstaxifyHTTPRequestHandler(BaseHTTPRequestHandler):
    # POST field containing file contents
    image_payload_field = "f"

    # Maximum acceptable payload size = 15MB (allow for full-size jpg, but ideally would be downsized/cropped already)
    max_payload_size = 15 * 1024 * 1024

    def do_GET(self):
        self.show_get_form()

    def do_POST(self):
        self.handle_post_data()

    def handle_post_data(self):
    
        print("\nClient: {} Payload Size: {} UA: {}".format(
            ':'.join(str(i) for i in self.client_address), 
            self.headers['Content-Length'],
            self.headers['User-Agent']
        ))

        # Don't accept large payloads; doesn't handle case when clients spoof this
        if int(self.headers['Content-Length']) > InstaxifyHTTPRequestHandler.max_payload_size:
            self.send_error(413, 'Image is too large.') 
            return
        # File uploads should have content-type of multipart/form-data
        if not self.headers['Content-Type'].startswith('multipart/form-data'):
            # Send error message
            self.send_error(400, 'Invalid request.')
            return

        # Extract file from payload, check that image is valid
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
            'REQUEST_METHOD': 'POST', 
            'CONTENT_TYPE': self.headers['Content-Type']}
        )
        
        try:
            file_data = form[InstaxifyHTTPRequestHandler.image_payload_field].file.read()
            filename = form[InstaxifyHTTPRequestHandler.image_payload_field].filename
            print("Filename: {}".format(filename))
           
            # Process image, return to client as image
            try:
                # Early detection of non-image (pythonic way would to try to parse and throw exception)
                if not magic.from_buffer(file_data, mime=True).startswith('image/'):
                    raise TypeError

                # should automatically call resp_bytes.close() to free BytesIO object when completed
                resp_bytes = instax.convert(file_data)
                resp_body = resp_bytes.getvalue()
                resp_type = magic.from_buffer(resp_body, mime=True);

                if not resp_type.startswith('image/'):
                    # Server failed to process image, give a 500-class response
                    self.send_error(500, 'Unable to process image.')
                else:
                    # Capture the image and encode to base64 so we can push to 
                    # browser as <img> and embed js code to download, since the
                    # image is not stored.

                    resp_buf = io.BytesIO()

                    # Show form before displaying image
                    resp_buf.write(self._get_form())

                    # TODO: Move this to convert class
                    conv_type = "instaxify"

                    # Craft download filename from original filename and mime type
                    conv_filename = "{}-{}.{}".format(
                        splitext(filename)[0],
                        conv_type,
                        resp_type.replace("image/", "")
                    )

                    #onclick = "alert(this.getAttribute(\"download\"))"
                    # Firefox requires link to be in the body to be clicked
                    onclick = '''
                        var link = document.createElement("a");
                        link.download = this.getAttribute("download");
                        link.href = this.getAttribute("src");
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    '''

                    # TODO: implement get img tag method in instaxify object
                    resp_buf.write("<img download='{}' src='data:{};base64,{}'\n onClick='{}' width='100%' />".format(
                        conv_filename, 
                        resp_type, 
                        base64.b64encode(resp_body).decode(),
                        onclick
                    ).encode())

                    # Get length of buffer for response length
                    length = resp_buf.tell()
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(length))
                    self.end_headers()
                    # Use getvalue instead of getbuffer view so we can close the bytesio object
                    self.wfile.write(resp_buf.getvalue())

                    # Free response buffer
                    resp_buf.close()

                # Cleanup
                del resp_body
                resp_bytes.close()
                
            except (IOError, TypeError):
                self.send_error(415, 'Invalid image format.')
                return
            finally:
                del file_data

        except KeyError:
            # Field image_payload_field doesn't exist in POST body
            self.send_error(400, 'No image specified.')
            return
        finally:
            # explicitly free memory
            del form

    def send_error(self, http_code, message):
        # Assume no responses have been sent
        self.send_response(http_code)
        if self._is_interactive():
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self._get_form())
            self.wfile.write(bytes(message, 'utf-8'))

        else:
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(bytes(message, 'utf-8'))

    def show_get_form(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(self._get_form())

    def _get_form(self):
        return(b'''
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>input { font-size: 4vw; }</style>
        <form action="/" method="post" enctype="multipart/form-data">
            <input type="file" name="f" />
            <input type="submit" value="Convert" />
        </form>
        
        ''')

    def _is_interactive(self):
        # TODO: guess whether this is interactive browser by UA so API-like
        # requests can skip generating forms or other user-friendly bits
        return True


httpd = HTTPServer(('', 8443), InstaxifyHTTPRequestHandler)

print("Starting conversion service.")

httpd.serve_forever()
