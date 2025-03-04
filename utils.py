import numpy as np
import cv2
import pickle


#########################################################################
# utils.py: Utilities used in LD and usage of Pickle for serialisation
#########################################################################

def nothing(x):
    pass


def remove_distortion(img, cal_dir='cal_pickle.p'):
    with open(cal_dir, mode='rb') as f:
        file = pickle.load(f)
    mtx = file['mtx']
    dist = file['dist']
    dst = cv2.undistort(img, mtx, dist, None, mtx)
    return dst


def initializeTrackPoints(intialTrackPointVals):
    cv2.namedWindow("Tracking Points")
    cv2.resizeWindow("Tracking Points", 360, 240)
    cv2.createTrackbar("Width Top", "Tracking Points", intialTrackPointVals[0], 50, nothing)
    cv2.createTrackbar("Height Top", "Tracking Points", intialTrackPointVals[1], 100, nothing)
    cv2.createTrackbar("Width Bottom", "Tracking Points", intialTrackPointVals[2], 50, nothing)
    cv2.createTrackbar("Height Bottom", "Tracking Points", intialTrackPointVals[3], 100, nothing)


def valTrackPoints():
    widthTop = cv2.getTrackbarPos("Width Top", "Tracking Points")
    heightTop = cv2.getTrackbarPos("Height Top", "Tracking Points")
    widthBottom = cv2.getTrackbarPos("Width Bottom", "Tracking Points")
    heightBottom = cv2.getTrackbarPos("Height Bottom", "Tracking Points")
    src = np.float32([(widthTop / 100, heightTop / 100), (1 - (widthTop / 100), heightTop / 100),
                      (widthBottom / 100, heightBottom / 100), (1 - (widthBottom / 100), heightBottom / 100)])
    return src


def drawPoints(img, src):
    img_size = np.float32([(img.shape[1], img.shape[0])])
    src = src * img_size
    for x in range(0, 4):
        cv2.circle(img, (int(src[x][0]), int(src[x][1])), 5, (255, 0, 255), cv2.FILLED)
    return img


def colourFilter(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lowerYellow = np.array([18, 94, 140])
    upperYellow = np.array([48, 255, 255])
    lowerWhite = np.array([0, 0, 200])
    upperWhite = np.array([255, 255, 255])
    maskedWhite = cv2.inRange(hsv, lowerWhite, upperWhite)
    maskedYellow = cv2.inRange(hsv, lowerYellow, upperYellow)
    combinedImage = cv2.bitwise_or(maskedWhite, maskedYellow)
    return combinedImage


def thresholding(img):
    imgGrey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kernel = np.ones((5, 5))
    imgBlur = cv2.GaussianBlur(imgGrey, (5, 5), 0)
    imgCanny = cv2.Canny(imgBlur, 50, 100)
    imgDial = cv2.dilate(imgCanny, kernel, iterations=1)
    imgErode = cv2.erode(imgDial, kernel, iterations=1)
    imgColour = colourFilter(img)
    combinedImage = cv2.bitwise_or(imgColour, imgErode)
    return combinedImage, imgCanny, imgColour


def pipeline(img, s_thresh=(100, 255), sx_thresh=(15, 255)):
    img = remove_distortion(img)
    img = np.copy(img)

    # Convert to HLS colour space and separate the V channel
    hls = cv2.cvtColor(img, cv2.COLOR_RGB2HLS).astype(np.float)
    l_channel = hls[:, :, 1]
    s_channel = hls[:, :, 2]
    h_channel = hls[:, :, 0]

    sobelx = cv2.Sobel(l_channel, cv2.CV_64F, 1, 1)  # Take the derivative in x
    abs_sobelx = np.absolute(sobelx)  # Absolute x derivative to accentuate lines away from horizontal
    scaled_sobel = np.uint8(255 * abs_sobelx / np.max(abs_sobelx))

    # Threshold x gradient
    sxbinary = np.zeros_like(scaled_sobel)
    sxbinary[(scaled_sobel >= sx_thresh[0]) & (scaled_sobel <= sx_thresh[1])] = 1

    # Threshold colour channel
    s_binary = np.zeros_like(s_channel)
    s_binary[(s_channel >= s_thresh[0]) & (s_channel <= s_thresh[1])] = 1

    combined_binary = np.zeros_like(sxbinary)
    combined_binary[(s_binary == 1) | (sxbinary == 1)] = 1
    return combined_binary


def get_hist(img):
    hist = np.sum(img[img.shape[0] // 2:, :], axis=0)
    return hist


left_a, left_b, left_c = [], [], []
right_a, right_b, right_c = [], [], []


def perspective_warp(img,
                     dst_size=(1280, 720),
                     src=np.float32([(0.43, 0.65), (0.58, 0.65), (0.1, 1), (1, 1)]),
                     dst=np.float32([(0, 0), (1, 0), (0, 1), (1, 1)])):
    img_size = np.float32([(img.shape[1], img.shape[0])])
    src = src * img_size
    dst = dst * np.float32(dst_size)

    # Calculate the perspective transform matrix
    matrix = cv2.getPerspectiveTransform(src, dst)

    # Warp the image using OpenCV warpPerspective()
    warped = cv2.warpPerspective(img, matrix, dst_size)
    return warped


def inv_perspective_warp(img,
                         dst_size=(1280, 720),
                         src=np.float32([(0, 0), (1, 0), (0, 1), (1, 1)]),
                         dst=np.float32([(0.43, 0.65), (0.58, 0.65), (0.1, 1), (1, 1)])):
    img_size = np.float32([(img.shape[1], img.shape[0])])
    src = src * img_size
    dst = dst * np.float32(dst_size)

    # Calculate the perspective transform matrix
    matrix = cv2.getPerspectiveTransform(src, dst)

    # Warp the image using OpenCV warpPerspective()
    warped = cv2.warpPerspective(img, matrix, dst_size)
    return warped


def sliding_window(img, nwindows=15, margin=50, minpix=1, draw_windows=True):
    global left_a, left_b, left_c, right_a, right_b, right_c
    left_fit_ = np.empty(3)
    right_fit_ = np.empty(3)
    out_img = np.dstack((img, img, img)) * 255
    histogram = get_hist(img)

    # find peaks on left and right side
    midpoint = int(histogram.shape[0] / 2)
    leftx_base = np.argmax(histogram[:midpoint])
    rightx_base = np.argmax(histogram[midpoint:]) + midpoint
    window_height = np.int(img.shape[0] / nwindows)

    # Identify coordinates of nonzero pixels
    nonzero = img.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])

    leftx_current = leftx_base
    rightx_current = rightx_base
    left_lane_inds = []
    right_lane_inds = []

    for window in range(nwindows):
        # Identify boundaries
        win_y_low = img.shape[0] - (window + 1) * window_height
        win_y_high = img.shape[0] - window * window_height
        win_xleft_low = leftx_current - margin
        win_xleft_high = leftx_current + margin
        win_xright_low = rightx_current - margin
        win_xright_high = rightx_current + margin

        # Draw the visualised image
        if draw_windows:
            cv2.rectangle(out_img, (win_xleft_low, win_y_low), (win_xleft_high, win_y_high),
                          (255, 0, 255), 1)
            cv2.rectangle(out_img, (win_xright_low, win_y_low), (win_xright_high, win_y_high),
                          (255, 0, 255), 1)

            # Identify nonzero pixels in window
        good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                          (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
        good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
                           (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]

        left_lane_inds.append(good_left_inds)
        right_lane_inds.append(good_right_inds)

        if len(good_left_inds) > minpix:
            leftx_current = np.int(np.mean(nonzerox[good_left_inds]))
        if len(good_right_inds) > minpix:
            rightx_current = np.int(np.mean(nonzerox[good_right_inds]))

    # Concatenate the arrays of indices
    left_lane_inds = np.concatenate(left_lane_inds)
    right_lane_inds = np.concatenate(right_lane_inds)

    # Extract left and right line pixel positions
    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds]
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]

    if leftx.size and rightx.size:
        # Fit second order polynomial
        left_fit = np.polyfit(lefty, leftx, 2)
        right_fit = np.polyfit(righty, rightx, 2)

        left_a.append(left_fit[0])
        left_b.append(left_fit[1])
        left_c.append(left_fit[2])

        right_a.append(right_fit[0])
        right_b.append(right_fit[1])
        right_c.append(right_fit[2])

        left_fit_[0] = np.mean(left_a[-10:])
        left_fit_[1] = np.mean(left_b[-10:])
        left_fit_[2] = np.mean(left_c[-10:])

        right_fit_[0] = np.mean(right_a[-10:])
        right_fit_[1] = np.mean(right_b[-10:])
        right_fit_[2] = np.mean(right_c[-10:])

        # Generate coordinates for plotting
        plot = np.linspace(0, img.shape[0] - 1, img.shape[0])
        left_fitx = left_fit_[0] * plot ** 2 + left_fit_[1] * plot + left_fit_[2]
        right_fitx = right_fit_[0] * plot ** 2 + right_fit_[1] * plot + right_fit_[2]

        out_img[nonzeroy[left_lane_inds], nonzerox[left_lane_inds]] = [0, 0, 255]
        out_img[nonzeroy[right_lane_inds], nonzerox[right_lane_inds]] = [255, 255, 255]

        return out_img, (left_fitx, right_fitx), (left_fit_, right_fit_), plot
    else:
        return img, (0, 0), (0, 0), 0


def get_curve(img, leftx, rightx):
    plot = np.linspace(0, img.shape[0] - 1, img.shape[0])
    y_eval = np.max(plot)
    ymeters_per_pix = 1 / img.shape[0]
    xmeters_per_pix = 0.1 / img.shape[0]

    # Fit polynomials to coordinates
    left_fit_cr = np.polyfit(plot * ymeters_per_pix, leftx * xmeters_per_pix, 2)
    right_fit_cr = np.polyfit(plot * ymeters_per_pix, rightx * xmeters_per_pix, 2)

    # Calculate radius of curvature is in meters
    car_pos = img.shape[1] / 2
    l_fit_x_int = left_fit_cr[0] * img.shape[0] ** 2 + left_fit_cr[1] * img.shape[0] + left_fit_cr[2]
    r_fit_x_int = right_fit_cr[0] * img.shape[0] ** 2 + right_fit_cr[1] * img.shape[0] + right_fit_cr[2]
    lane_center_position = (r_fit_x_int + l_fit_x_int) / 2
    center = (car_pos - lane_center_position) * xmeters_per_pix / 10
    return l_fit_x_int, r_fit_x_int, center


def draw_lanes(img, left_fit, right_fit, frameWidth, frameHeight, src):
    plot = np.linspace(0, img.shape[0] - 1, img.shape[0])
    colour_img = np.zeros_like(img)

    left = np.array([np.transpose(np.vstack([left_fit, plot]))])
    right = np.array([np.flipud(np.transpose(np.vstack([right_fit, plot])))])
    points = np.hstack((left, right))

    cv2.fillPoly(colour_img, np.int_(points), (255, 0, 0))
    inv_perspective = inv_perspective_warp(colour_img, (frameWidth, frameHeight), dst=src)
    inv_perspective = cv2.addWeighted(img, 0.5, inv_perspective, 0.7, 0)
    return inv_perspective


def stackImages(scale, imgArray):
    rows = len(imgArray)
    cols = len(imgArray[0])
    rowsAvailable = isinstance(imgArray[0], list)
    width = imgArray[0][0].shape[1]
    height = imgArray[0][0].shape[0]
    if rowsAvailable:
        for x in range(0, rows):
            for y in range(0, cols):
                if imgArray[x][y].shape[:2] == imgArray[0][0].shape[:2]:
                    imgArray[x][y] = cv2.resize(imgArray[x][y], (0, 0), None, scale, scale)
                else:
                    imgArray[x][y] = cv2.resize(imgArray[x][y], (imgArray[0][0].shape[1], imgArray[0][0].shape[0]),
                                                None, scale, scale)
                if len(imgArray[x][y].shape) == 2: imgArray[x][y] = cv2.cvtColor(imgArray[x][y], cv2.COLOR_GRAY2BGR)
        imageBlank = np.zeros((height, width, 3), np.uint8)
        hor = [imageBlank] * rows
        for x in range(0, rows):
            hor[x] = np.hstack(imgArray[x])
        ver = np.vstack(hor)
    else:
        for x in range(0, rows):
            if imgArray[x].shape[:2] == imgArray[0].shape[:2]:
                imgArray[x] = cv2.resize(imgArray[x], (0, 0), None, scale, scale)
            else:
                imgArray[x] = cv2.resize(imgArray[x], (imgArray[0].shape[1], imgArray[0].shape[0]), None, scale, scale)
            if len(imgArray[x].shape) == 2: imgArray[x] = cv2.cvtColor(imgArray[x], cv2.COLOR_GRAY2BGR)
        hor = np.hstack(imgArray)
        ver = hor
    return ver


def drawLines(img, lane_curve):
    myWidth = img.shape[1]
    myHeight = img.shape[0]
    print(myWidth, myHeight)
    for x in range(-30, 30):
        w = myWidth // 20
        cv2.line(img, (w * x + int(lane_curve // 100), myHeight - 30),
                 (w * x + int(lane_curve // 100), myHeight), (0, 255, 255), 2)
    cv2.line(img, (int(lane_curve // 100) + myWidth // 2, myHeight - 30),
             (int(lane_curve // 100) + myWidth // 2, myHeight), (0, 255, 255), 3)
    cv2.line(img, (myWidth // 2, myHeight - 50), (myWidth // 2, myHeight), (0, 0, 255), 2)
    return img
