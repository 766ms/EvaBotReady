// Carrusel de avatares. Se carga aparte (React.lazy): Swiper solo se descarga cuando se abre esta pantalla.
import { Swiper, SwiperSlide } from 'swiper/react';
import { EffectCoverflow, Keyboard, Navigation } from 'swiper/modules';
import 'swiper/css/navigation';
import 'swiper/css';
import 'swiper/css/effect-coverflow';

export default function AvatarPicker({ avatars, initialIndex = 0, onChange }) {
  return (
    <>
      <Swiper
        effect={'coverflow'}
        grabCursor={true}
        centeredSlides={true}
        slidesPerView={'auto'}
        initialSlide={initialIndex}
        keyboard={{ enabled: true }}
        navigation={{
          nextEl: '.swiper-button-next',
          prevEl: '.swiper-button-prev',
        }}
        coverflowEffect={{
          rotate: 0,
          stretch: 0,
          depth: 100,
          modifier: 2.5,
          slideShadows: false,
        }}
        modules={[EffectCoverflow, Keyboard, Navigation]}
        className="mySwiper"
        onSlideChange={(swiper) => onChange(swiper.activeIndex)}
      >
        {avatars.map((img, index) => (
          <SwiperSlide key={index}>
            <img src={img} alt={`Avatar ${index + 1}`} className="carousel-img-swiper" tabIndex={0} width="120" height="120" decoding="async" />
          </SwiperSlide>
        ))}
      </Swiper>

      <div className="carousel-navigation">
        <div className="swiper-button-prev"></div>
        <div className="swiper-button-next"></div>
      </div>
    </>
  );
}
